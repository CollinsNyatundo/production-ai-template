"""AWS SQS (with native DLQ RedrivePolicy) and DynamoDB multi-tenant state adapters."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import List, Optional, cast

from botocore.exceptions import ClientError

from app.cloud.client import AWSClientFactory, aws_client_factory
from app.config import settings
from app.types import JSONDict

logger = logging.getLogger("app.cloud.queue_store")


@dataclass(frozen=True)
class QueuedMessage:
    message_id: str
    receipt_handle: str
    body: JSONDict
    receive_count: int = 1


class SQSIngestionQueue:
    """SQS producer/consumer supporting native visibility timeout and DLQ redrive."""

    def __init__(
        self,
        factory: AWSClientFactory = aws_client_factory,
        queue_url: Optional[str] = None,
    ) -> None:
        self._factory = factory
        self._queue_url = queue_url

    @property
    def queue_url(self) -> str:
        return self._queue_url or settings.aws_sqs_queue_url

    def _send_sync(self, payload: JSONDict, target_url: str) -> str:
        sqs = self._factory.get_client("sqs")
        resp = sqs.send_message(QueueUrl=target_url, MessageBody=json.dumps(payload))
        return str(resp["MessageId"])

    def _receive_sync(self, target_url: str, max_messages: int, wait_seconds: int) -> List[QueuedMessage]:
        sqs = self._factory.get_client("sqs")
        resp = sqs.receive_message(
            QueueUrl=target_url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=wait_seconds,
            AttributeNames=["ApproximateReceiveCount"],
        )
        out: List[QueuedMessage] = []
        for raw in resp.get("Messages", []):
            parsed = json.loads(str(raw["Body"]))
            body: JSONDict = parsed if isinstance(parsed, dict) else {"value": parsed}
            attrs = raw.get("Attributes", {})
            raw_count = attrs.get("ApproximateReceiveCount", 1) if isinstance(attrs, dict) else 1
            try:
                receive_count = max(1, int(raw_count))
            except (TypeError, ValueError):
                receive_count = 1
            out.append(
                QueuedMessage(
                    message_id=str(raw["MessageId"]),
                    receipt_handle=str(raw["ReceiptHandle"]),
                    body=body,
                    receive_count=receive_count,
                )
            )
        return out

    def _delete_sync(self, target_url: str, receipt_handle: str) -> None:
        sqs = self._factory.get_client("sqs")
        sqs.delete_message(QueueUrl=target_url, ReceiptHandle=receipt_handle)

    def _change_visibility_sync(self, target_url: str, receipt_handle: str, visibility_timeout: int) -> None:
        sqs = self._factory.get_client("sqs")
        sqs.change_message_visibility(
            QueueUrl=target_url,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=visibility_timeout,
        )

    def _get_max_receive_count_sync(self, target_url: str) -> Optional[int]:
        sqs = self._factory.get_client("sqs")
        try:
            resp = sqs.get_queue_attributes(QueueUrl=target_url, AttributeNames=["RedrivePolicy"])
            raw_policy = resp.get("Attributes", {}).get("RedrivePolicy")
            if isinstance(raw_policy, str) and raw_policy.strip():
                policy = json.loads(raw_policy)
                if isinstance(policy, dict) and "maxReceiveCount" in policy:
                    return max(1, int(policy["maxReceiveCount"]))
        except (ClientError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return None

    async def enqueue_job(self, job_payload: JSONDict, queue_url: Optional[str] = None) -> str:
        url = queue_url or self.queue_url
        if not url:
            raise ValueError("AWS_SQS_QUEUE_URL is required to enqueue ingestion jobs.")
        return await asyncio.to_thread(self._send_sync, job_payload, url)

    async def receive_jobs(
        self,
        max_messages: int = 1,
        wait_seconds: int = 1,
        queue_url: Optional[str] = None,
    ) -> List[QueuedMessage]:
        url = queue_url or self.queue_url
        if not url:
            raise ValueError("AWS_SQS_QUEUE_URL is required to receive ingestion jobs.")
        return await asyncio.to_thread(self._receive_sync, url, max_messages, wait_seconds)

    async def acknowledge(self, receipt_handle: str, queue_url: Optional[str] = None) -> None:
        url = queue_url or self.queue_url
        if not url:
            raise ValueError("AWS_SQS_QUEUE_URL is required to acknowledge messages.")
        await asyncio.to_thread(self._delete_sync, url, receipt_handle)

    async def extend_visibility(
        self,
        receipt_handle: str,
        visibility_timeout: int,
        queue_url: Optional[str] = None,
    ) -> None:
        """Extend an in-flight SQS message's visibility timeout."""
        url = queue_url or self.queue_url
        if not url:
            return
        await asyncio.to_thread(self._change_visibility_sync, url, receipt_handle, visibility_timeout)

    async def get_max_receive_count(self, queue_url: Optional[str] = None) -> Optional[int]:
        """Return ``maxReceiveCount`` from the queue's RedrivePolicy, or ``None`` if unavailable."""
        url = queue_url or self.queue_url
        if not url:
            return None
        return await asyncio.to_thread(self._get_max_receive_count_sync, url)


class DynamoDBStateRepository:
    """Tenant-partitioned DynamoDB repository for feedback, ingestion state, collections, and cache generations."""

    def __init__(
        self,
        factory: AWSClientFactory = aws_client_factory,
        table_name: Optional[str] = None,
    ) -> None:
        self._factory = factory
        self._table_name = table_name

    @property
    def table_name(self) -> str:
        return self._table_name or settings.aws_dynamodb_table

    def _put_feedback_sync(
        self,
        tenant_id: str,
        session_id: str,
        rating: str,
        comment: str,
    ) -> str:
        ddb = self._factory.get_client("dynamodb")
        feedback_id = f"fb-{uuid.uuid4().hex[:10]}"
        sk = f"FEEDBACK#{session_id}#{feedback_id}"
        ddb.put_item(
            TableName=self.table_name,
            Item={
                "tenant_id": {"S": tenant_id},
                "item_key": {"S": sk},
                "session_id": {"S": session_id},
                "rating": {"S": rating},
                "comment": {"S": comment},
                "created_at": {"S": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
            },
        )
        return feedback_id

    def _list_feedback_sync(self, tenant_id: str, session_id: Optional[str] = None) -> List[dict[str, str]]:
        ddb = self._factory.get_client("dynamodb")
        prefix = f"FEEDBACK#{session_id}#" if session_id else "FEEDBACK#"
        rows: List[dict[str, str]] = []
        last_key: Optional[dict[str, object]] = None
        while True:
            if last_key is not None:
                resp = ddb.query(
                    TableName=self.table_name,
                    KeyConditionExpression="tenant_id = :t AND begins_with(item_key, :p)",
                    ExpressionAttributeValues={":t": {"S": tenant_id}, ":p": {"S": prefix}},
                    ExclusiveStartKey=last_key,
                    ConsistentRead=True,
                )
            else:
                resp = ddb.query(
                    TableName=self.table_name,
                    KeyConditionExpression="tenant_id = :t AND begins_with(item_key, :p)",
                    ExpressionAttributeValues={":t": {"S": tenant_id}, ":p": {"S": prefix}},
                    ConsistentRead=True,
                )
            for item in resp.get("Items", []):
                rows.append(
                    {
                        "tenant_id": str(item["tenant_id"]["S"]),
                        "item_key": str(item["item_key"]["S"]),
                        "session_id": str(item["session_id"]["S"]),
                        "rating": str(item["rating"]["S"]),
                        "comment": str(item.get("comment", {}).get("S", "")),
                        "created_at": str(item.get("created_at", {}).get("S", "")),
                    }
                )
            next_key = resp.get("LastEvaluatedKey")
            if not isinstance(next_key, dict) or not next_key:
                break
            last_key = next_key
        return rows

    def _put_ingestion_job_sync(
        self,
        tenant_id: str,
        job: JSONDict,
        lease_owner: Optional[str] = None,
        lease_expires_at: Optional[int] = None,
    ) -> None:
        ddb = self._factory.get_client("dynamodb")
        job_id = str(job["job_id"])
        item: dict[str, dict[str, str]] = {
            "tenant_id": {"S": tenant_id},
            "item_key": {"S": f"JOB#{job_id}"},
            "job_id": {"S": job_id},
            "status": {"S": str(job.get("status", "processing"))},
            "payload": {"S": json.dumps(job)},
            "updated_at": {"S": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
        }
        if lease_owner is not None:
            item["lease_owner"] = {"S": lease_owner}
        if lease_expires_at is not None:
            item["lease_expires_at"] = {"N": str(lease_expires_at)}
        ddb.put_item(TableName=self.table_name, Item=item)

    def _get_ingestion_job_sync(self, tenant_id: str, job_id: str) -> Optional[JSONDict]:
        ddb = self._factory.get_client("dynamodb")
        resp = ddb.get_item(
            TableName=self.table_name,
            Key={"tenant_id": {"S": tenant_id}, "item_key": {"S": f"JOB#{job_id}"}},
            ConsistentRead=True,
        )
        item = resp.get("Item")
        if not isinstance(item, dict):
            return None
        raw_payload = item.get("payload", {}).get("S")
        if not isinstance(raw_payload, str):
            return None
        parsed = json.loads(raw_payload)
        return cast(JSONDict, parsed) if isinstance(parsed, dict) else None

    def _claim_ingestion_job_sync(
        self,
        tenant_id: str,
        job: JSONDict,
        owner_id: str,
        lease_seconds: int,
    ) -> str:
        """Atomically claim a tenant-scoped ingestion lease.

        Returns:
            ``"acquired"`` when this worker owns the lease, ``"completed"`` when the
            job has already finished, or ``"in_progress"`` when another active worker
            holds a non-expired lease.
        """
        ddb = self._factory.get_client("dynamodb")
        job_id = str(job["job_id"])
        now_ts = int(time.time())
        expires_at = now_ts + max(5, lease_seconds)
        sk = f"JOB#{job_id}"

        existing_resp = ddb.get_item(
            TableName=self.table_name,
            Key={"tenant_id": {"S": tenant_id}, "item_key": {"S": sk}},
            ConsistentRead=True,
        )
        existing = existing_resp.get("Item")
        if isinstance(existing, dict) and existing.get("status", {}).get("S") == "completed":
            return "completed"

        payload_json = json.dumps(job)
        try:
            ddb.put_item(
                TableName=self.table_name,
                Item={
                    "tenant_id": {"S": tenant_id},
                    "item_key": {"S": sk},
                    "job_id": {"S": job_id},
                    "status": {"S": "processing"},
                    "payload": {"S": payload_json},
                    "lease_owner": {"S": owner_id},
                    "lease_expires_at": {"N": str(expires_at)},
                    "updated_at": {"S": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                },
                ConditionExpression=(
                    "attribute_not_exists(item_key) OR "
                    "(#st <> :completed AND "
                    "(attribute_not_exists(lease_expires_at) OR lease_expires_at <= :now OR lease_owner = :owner))"
                ),
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={
                    ":completed": {"S": "completed"},
                    ":now": {"N": str(now_ts)},
                    ":owner": {"S": owner_id},
                },
            )
            return "acquired"
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code != "ConditionalCheckFailedException":
                raise
            latest = ddb.get_item(
                TableName=self.table_name,
                Key={"tenant_id": {"S": tenant_id}, "item_key": {"S": sk}},
                ConsistentRead=True,
            ).get("Item")
            if isinstance(latest, dict) and latest.get("status", {}).get("S") == "completed":
                return "completed"
            return "in_progress"

    def _renew_ingestion_lease_sync(
        self,
        tenant_id: str,
        job_id: str,
        owner_id: str,
        lease_seconds: int,
    ) -> bool:
        ddb = self._factory.get_client("dynamodb")
        expires_at = int(time.time()) + max(5, lease_seconds)
        try:
            ddb.update_item(
                TableName=self.table_name,
                Key={"tenant_id": {"S": tenant_id}, "item_key": {"S": f"JOB#{job_id}"}},
                UpdateExpression="SET lease_expires_at = :exp, updated_at = :ts",
                ConditionExpression="lease_owner = :owner AND #st <> :completed",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={
                    ":exp": {"N": str(expires_at)},
                    ":ts": {"S": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                    ":owner": {"S": owner_id},
                    ":completed": {"S": "completed"},
                },
            )
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise

    def _put_collection_sync(self, tenant_id: str, collection: JSONDict) -> None:
        ddb = self._factory.get_client("dynamodb")
        col_id = str(collection["id"])
        ddb.put_item(
            TableName=self.table_name,
            Item={
                "tenant_id": {"S": tenant_id},
                "item_key": {"S": f"COLLECTION#{col_id}"},
                "collection_id": {"S": col_id},
                "payload": {"S": json.dumps(collection)},
                "updated_at": {"S": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
            },
        )

    def _get_collection_sync(self, tenant_id: str, collection_id: str) -> Optional[JSONDict]:
        ddb = self._factory.get_client("dynamodb")
        resp = ddb.get_item(
            TableName=self.table_name,
            Key={"tenant_id": {"S": tenant_id}, "item_key": {"S": f"COLLECTION#{collection_id}"}},
            ConsistentRead=True,
        )
        item = resp.get("Item")
        if not isinstance(item, dict):
            return None
        raw_payload = item.get("payload", {}).get("S")
        if not isinstance(raw_payload, str):
            return None
        parsed = json.loads(raw_payload)
        return cast(JSONDict, parsed) if isinstance(parsed, dict) else None

    def _list_collections_sync(self, tenant_id: str) -> List[JSONDict]:
        ddb = self._factory.get_client("dynamodb")
        rows: List[JSONDict] = []
        last_key: Optional[dict[str, object]] = None
        while True:
            if last_key is not None:
                resp = ddb.query(
                    TableName=self.table_name,
                    KeyConditionExpression="tenant_id = :t AND begins_with(item_key, :p)",
                    ExpressionAttributeValues={":t": {"S": tenant_id}, ":p": {"S": "COLLECTION#"}},
                    ExclusiveStartKey=last_key,
                    ConsistentRead=True,
                )
            else:
                resp = ddb.query(
                    TableName=self.table_name,
                    KeyConditionExpression="tenant_id = :t AND begins_with(item_key, :p)",
                    ExpressionAttributeValues={":t": {"S": tenant_id}, ":p": {"S": "COLLECTION#"}},
                    ConsistentRead=True,
                )
            for item in resp.get("Items", []):
                raw_payload = item.get("payload", {}).get("S")
                if isinstance(raw_payload, str):
                    parsed = json.loads(raw_payload)
                    if isinstance(parsed, dict):
                        rows.append(cast(JSONDict, parsed))
            next_key = resp.get("LastEvaluatedKey")
            if not isinstance(next_key, dict) or not next_key:
                break
            last_key = next_key
        return rows

    def _delete_collection_sync(self, tenant_id: str, collection_id: str) -> bool:
        ddb = self._factory.get_client("dynamodb")
        resp = ddb.delete_item(
            TableName=self.table_name,
            Key={"tenant_id": {"S": tenant_id}, "item_key": {"S": f"COLLECTION#{collection_id}"}},
            ReturnValues="ALL_OLD",
        )
        return "Attributes" in resp

    def _get_cache_generation_sync(self, tenant_id: str) -> int:
        ddb = self._factory.get_client("dynamodb")
        resp = ddb.get_item(
            TableName=self.table_name,
            Key={"tenant_id": {"S": tenant_id}, "item_key": {"S": "CACHE_GEN"}},
            ConsistentRead=True,
        )
        item = resp.get("Item")
        if not isinstance(item, dict):
            return 0
        raw_gen = item.get("generation", {}).get("N")
        try:
            return int(raw_gen) if raw_gen is not None else 0
        except (TypeError, ValueError):
            return 0

    def _increment_cache_generation_sync(self, tenant_id: str) -> int:
        ddb = self._factory.get_client("dynamodb")
        resp = ddb.update_item(
            TableName=self.table_name,
            Key={"tenant_id": {"S": tenant_id}, "item_key": {"S": "CACHE_GEN"}},
            UpdateExpression="ADD generation :inc",
            ExpressionAttributeValues={":inc": {"N": "1"}},
            ReturnValues="UPDATED_NEW",
        )
        raw_gen = resp.get("Attributes", {}).get("generation", {}).get("N", "1")
        return int(raw_gen)

    async def put_feedback(
        self,
        tenant_id: str,
        session_id: str,
        rating: str,
        comment: str = "",
    ) -> str:
        return await asyncio.to_thread(self._put_feedback_sync, tenant_id, session_id, rating, comment)

    async def list_feedback(self, tenant_id: str, session_id: Optional[str] = None) -> List[dict[str, str]]:
        return await asyncio.to_thread(self._list_feedback_sync, tenant_id, session_id)

    async def put_ingestion_job(
        self,
        tenant_id: str,
        job: JSONDict,
        lease_owner: Optional[str] = None,
        lease_expires_at: Optional[int] = None,
    ) -> None:
        """Persist tenant-scoped ingestion job status to DynamoDB."""
        await asyncio.to_thread(self._put_ingestion_job_sync, tenant_id, job, lease_owner, lease_expires_at)

    async def get_ingestion_job(self, tenant_id: str, job_id: str) -> Optional[JSONDict]:
        """Fetch tenant-scoped ingestion job status from DynamoDB."""
        return await asyncio.to_thread(self._get_ingestion_job_sync, tenant_id, job_id)

    async def claim_ingestion_job(
        self,
        tenant_id: str,
        job: JSONDict,
        owner_id: str,
        lease_seconds: int = 30,
    ) -> str:
        """Atomically acquire an ingestion execution lease or report completed/in-progress."""
        return await asyncio.to_thread(self._claim_ingestion_job_sync, tenant_id, job, owner_id, lease_seconds)

    async def renew_ingestion_lease(
        self,
        tenant_id: str,
        job_id: str,
        owner_id: str,
        lease_seconds: int = 30,
    ) -> bool:
        """Extend an active ingestion execution lease if still owned by ``owner_id``."""
        return await asyncio.to_thread(self._renew_ingestion_lease_sync, tenant_id, job_id, owner_id, lease_seconds)

    async def put_collection(self, tenant_id: str, collection: JSONDict) -> None:
        """Persist tenant-scoped collection metadata to DynamoDB."""
        await asyncio.to_thread(self._put_collection_sync, tenant_id, collection)

    async def get_collection(self, tenant_id: str, collection_id: str) -> Optional[JSONDict]:
        """Fetch tenant-scoped collection metadata from DynamoDB."""
        return await asyncio.to_thread(self._get_collection_sync, tenant_id, collection_id)

    async def list_collections(self, tenant_id: str) -> List[JSONDict]:
        """List all persisted collections for a tenant from DynamoDB."""
        return await asyncio.to_thread(self._list_collections_sync, tenant_id)

    async def delete_collection(self, tenant_id: str, collection_id: str) -> bool:
        """Delete tenant-scoped collection metadata from DynamoDB."""
        return await asyncio.to_thread(self._delete_collection_sync, tenant_id, collection_id)

    async def get_cache_generation(self, tenant_id: str) -> int:
        """Read the shared monotonic cache invalidation generation for ``tenant_id``."""
        return await asyncio.to_thread(self._get_cache_generation_sync, tenant_id)

    async def increment_cache_generation(self, tenant_id: str) -> int:
        """Atomically advance the shared cache generation counter for ``tenant_id``."""
        return await asyncio.to_thread(self._increment_cache_generation_sync, tenant_id)


sqs_ingestion_queue = SQSIngestionQueue()
dynamodb_state_repo = DynamoDBStateRepository()
