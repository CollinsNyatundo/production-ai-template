"""Idempotent resource bootstrapper for AWS Emulator (or real AWS accounts).

Provisions:
  1. S3 document archive bucket (path-style compatible)
  2. Amazon S3 Vectors bucket for tenant-isolated RAG indices
  3. KMS symmetric key for tenant-bound EncryptionContext envelope encryption
  4. Secrets Manager JWT signing secret
  5. SQS ingestion DLQ + primary queue with native RedrivePolicy
  6. DynamoDB multi-tenant state table (waits until CREATING -> ACTIVE)
  7. CloudWatch Logs group for structured runtime spans
"""

from __future__ import annotations

import argparse
import json
import secrets
from typing import Dict

from botocore.exceptions import ClientError

from app.cloud.client import AWSClientFactory
from app.config import settings


def bootstrap_aws_resources(
    factory: AWSClientFactory | None = None,
    s3_bucket: str | None = None,
    s3_vector_bucket: str | None = None,
    jwt_secret_name: str | None = None,
    dynamodb_table: str | None = None,
    log_group: str | None = None,
    queue_prefix: str = "production-ai-ingest",
) -> Dict[str, str]:
    """Provision all required AWS resources idempotently and return their identifiers."""
    client_factory = factory or AWSClientFactory()
    bucket = s3_bucket or settings.aws_s3_bucket
    vec_bucket = s3_vector_bucket or settings.aws_s3_vector_bucket
    secret_name = jwt_secret_name or settings.aws_jwt_secret_name
    table_name = dynamodb_table or settings.aws_dynamodb_table
    cw_log_group = log_group or settings.aws_cloudwatch_log_group

    # 1. S3 Bucket (AWS requires LocationConstraint outside us-east-1)
    s3 = client_factory.get_client("s3")
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError:
        if client_factory.region_name == "us-east-1":
            s3.create_bucket(Bucket=bucket)
        else:
            s3.create_bucket(
                Bucket=bucket,
                CreateBucketConfiguration={"LocationConstraint": client_factory.region_name},
            )

    # 2. S3 Vectors Bucket
    s3v = client_factory.get_client("s3vectors")
    try:
        s3v.get_vector_bucket(vectorBucketName=vec_bucket)
    except ClientError:
        try:
            s3v.create_vector_bucket(vectorBucketName=vec_bucket)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if "Conflict" not in code and "AlreadyExists" not in code:
                raise

    # 3. KMS Symmetric Key (reuse alias if present)
    kms = client_factory.get_client("kms")
    alias_name = f"alias/{queue_prefix}-tenant-key"
    kms_key_id = ""
    try:
        aliases = kms.list_aliases().get("Aliases", [])
        for alias in aliases:
            if alias.get("AliasName") == alias_name and alias.get("TargetKeyId"):
                kms_key_id = str(alias["TargetKeyId"])
                break
    except ClientError:
        kms_key_id = ""

    if not kms_key_id:
        kms_key_id = str(
            kms.create_key(Description="Production AI Template tenant envelope key")["KeyMetadata"]["KeyId"]
        )
        try:
            kms.create_alias(AliasName=alias_name, TargetKeyId=kms_key_id)
        except ClientError:
            pass

    # 4. Secrets Manager JWT signing secret
    sm = client_factory.get_client("secretsmanager")
    jwt_secret_val = secrets.token_urlsafe(32)
    try:
        existing = sm.get_secret_value(SecretId=secret_name)
        parsed = json.loads(str(existing.get("SecretString", "{}")))
        jwt_secret_val = str(parsed.get("JWT_SECRET", jwt_secret_val))
    except ClientError:
        sm.create_secret(
            Name=secret_name,
            SecretString=json.dumps({"JWT_SECRET": jwt_secret_val}),
        )

    # 5. SQS DLQ + Primary Ingestion Queue with native RedrivePolicy
    sqs = client_factory.get_client("sqs")
    dlq_url = str(sqs.create_queue(QueueName=f"{queue_prefix}-dlq")["QueueUrl"])
    dlq_arn = str(sqs.get_queue_attributes(QueueUrl=dlq_url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"])
    main_url = str(
        sqs.create_queue(
            QueueName=queue_prefix,
            Attributes={
                "VisibilityTimeout": "5",
                "RedrivePolicy": json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "2"}),
            },
        )["QueueUrl"]
    )

    # 6. DynamoDB multi-tenant state table (honor real AWS CREATING -> ACTIVE lifecycle)
    ddb = client_factory.get_client("dynamodb")
    try:
        ddb.describe_table(TableName=table_name)
    except ClientError:
        ddb.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": "tenant_id", "KeyType": "HASH"},
                {"AttributeName": "item_key", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "tenant_id", "AttributeType": "S"},
                {"AttributeName": "item_key", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
    ddb.get_waiter("table_exists").wait(TableName=table_name, WaiterConfig={"Delay": 1, "MaxAttempts": 15})

    # 7. CloudWatch Log Group
    logs = client_factory.get_client("logs")
    try:
        logs.create_log_group(logGroupName=cw_log_group)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ResourceAlreadyExistsException":
            raise

    return {
        "AWS_S3_BUCKET": bucket,
        "AWS_S3_VECTOR_BUCKET": vec_bucket,
        "AWS_KMS_KEY_ID": kms_key_id,
        "AWS_JWT_SECRET_NAME": secret_name,
        "AWS_SQS_QUEUE_URL": main_url,
        "AWS_SQS_DLQ_URL": dlq_url,
        "AWS_DYNAMODB_TABLE": table_name,
        "AWS_CLOUDWATCH_LOG_GROUP": cw_log_group,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap AWS Emulator resources for production-ai-template.")
    parser.add_argument("--format", choices=["json", "env"], default="json")
    parser.add_argument("--env-file", default="", help="Optional path to write KEY=VALUE environment lines.")
    args = parser.parse_args()

    result = bootstrap_aws_resources()
    if args.env_file:
        with open(args.env_file, "w", encoding="utf-8") as fh:
            for key, value in result.items():
                fh.write(f"{key}={value}\n")
    if args.format == "env":
        for key, value in result.items():
            print(f"{key}={value}")
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
