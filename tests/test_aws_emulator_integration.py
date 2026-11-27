"""Live integration tests against aws/aws-emulator (ZERO mocks).

Run with a live aws-emulator container on https://127.0.0.1:9297 and standard env vars:
  AWS_ENDPOINT_URL, AWS_CA_BUNDLE, AWS_SHARED_CREDENTIALS_FILE, AWS_CONFIG_FILE,
  AWS_EC2_METADATA_DISABLED=true, AWS_DISABLE_HOST_PREFIX_INJECTION=true, AWS_REGION=us-east-1
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from typing import Dict

import pytest

from app.cloud.client import AWSClientFactory
from app.cloud.queue_store import DynamoDBStateRepository, SQSIngestionQueue
from app.cloud.secrets import AWSSecretsProvider, KMSEnvelopeCipher
from app.cloud.telemetry import AWSObservabilitySink
from app.cloud.vector_store import S3VectorKnowledgeStore, deterministic_embed
from app.components.hybrid_retriever import HybridRetriever
from app.config import settings
from app.security.auth import create_access_token, get_current_user
from app.services.ingestion_service import (
    create_ingestion_job,
    delete_collection_async,
    get_job_status,
    process_ingestion_job,
)
from app.services.semantic_cache import semantic_cache
from observability.feedback import feedback_tracker
from observability.tracer import current_user_context, tracer
from scripts.bootstrap_aws_emulator import bootstrap_aws_resources

pytestmark = pytest.mark.aws_emulator

_HAS_EMULATOR_ENV = bool(os.environ.get("AWS_ENDPOINT_URL") and os.environ.get("AWS_CA_BUNDLE"))


@pytest.fixture(scope="module")
def emulator_resources() -> Dict[str, str]:
    if not _HAS_EMULATOR_ENV:
        pytest.skip("AWS_ENDPOINT_URL and AWS_CA_BUNDLE must be set to run live aws_emulator tests.")
    suffix = uuid.uuid4().hex[:6]
    factory = AWSClientFactory()
    resources = bootstrap_aws_resources(
        factory=factory,
        s3_bucket=f"prod-ai-docs-{suffix}",
        s3_vector_bucket=f"prod-ai-vecs-{suffix}",
        jwt_secret_name=f"prod-ai-jwt-{suffix}",
        dynamodb_table=f"prod-ai-state-{suffix}",
        log_group=f"/prod-ai-template/test-{suffix}",
        queue_prefix=f"prod-ai-ingest-{suffix}",
    )
    # Prove bootstrap is genuinely idempotent on second call
    second = bootstrap_aws_resources(
        factory=factory,
        s3_bucket=resources["AWS_S3_BUCKET"],
        s3_vector_bucket=resources["AWS_S3_VECTOR_BUCKET"],
        jwt_secret_name=resources["AWS_JWT_SECRET_NAME"],
        dynamodb_table=resources["AWS_DYNAMODB_TABLE"],
        log_group=resources["AWS_CLOUDWATCH_LOG_GROUP"],
        queue_prefix=f"prod-ai-ingest-{suffix}",
    )
    assert second["AWS_KMS_KEY_ID"] == resources["AWS_KMS_KEY_ID"]
    sqs_client = factory.get_client("sqs")
    q_attrs = sqs_client.get_queue_attributes(
        QueueUrl=resources["AWS_SQS_QUEUE_URL"],
        AttributeNames=["VisibilityTimeout", "RedrivePolicy"],
    )["Attributes"]
    assert q_attrs["VisibilityTimeout"] == "30"
    redrive = json.loads(str(q_attrs["RedrivePolicy"]))
    assert int(redrive["maxReceiveCount"]) == 3
    return resources


@pytest.mark.asyncio
async def test_kms_cryptographic_tenant_isolation(emulator_resources: Dict[str, str]) -> None:
    """Ciphertext encrypted for tenant-alpha (including >4 KiB chunks) MUST fail under tenant-beta."""
    factory = AWSClientFactory()
    cipher = KMSEnvelopeCipher(factory=factory, key_id=emulator_resources["AWS_KMS_KEY_ID"])

    plaintext = "Confidential Kenyan M-Pesa reconciliation policy for Tenant Alpha. " + (
        "Paragraph extension exceeding the 4,096-byte KMS direct Encrypt limit. " * 90
    )
    assert len(plaintext.encode("utf-8")) > 4096
    ciphertext_b64 = await cipher.encrypt_text("tenant-alpha", plaintext)
    assert "Nairobi" not in ciphertext_b64 and "M-Pesa" not in ciphertext_b64
    assert await cipher.decrypt_text("tenant-alpha", ciphertext_b64) == plaintext

    with pytest.raises(PermissionError, match="KMS decryption rejected"):
        await cipher.decrypt_text("tenant-beta", ciphertext_b64)


@pytest.mark.asyncio
async def test_secrets_manager_jwt_auth_roundtrip(
    emulator_resources: Dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JWT tokens signed with the Secrets Manager key authenticate via get_current_user."""
    monkeypatch.setattr(settings, "aws_backend_enabled", True)
    monkeypatch.setattr(settings, "aws_jwt_secret_name", emulator_resources["AWS_JWT_SECRET_NAME"])

    provider = AWSSecretsProvider(factory=AWSClientFactory())
    secret_val = await provider.get_jwt_secret()
    assert len(secret_val) >= 20

    token = create_access_token({"sub": "admin"}, secret_key=secret_val)
    user = await get_current_user(token=token, api_key=None)
    assert user.username == "admin"
    assert user.tenant_id == "tenant-alpha"


@pytest.mark.asyncio
async def test_s3_vectors_and_kms_multi_tenant_rag_isolation(
    emulator_resources: Dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ingested tenant chunks are KMS-encrypted in S3, indexed in S3 Vectors, and strictly tenant-isolated."""
    monkeypatch.setattr(settings, "aws_backend_enabled", True)
    monkeypatch.setattr(settings, "aws_s3_bucket", emulator_resources["AWS_S3_BUCKET"])
    monkeypatch.setattr(settings, "aws_s3_vector_bucket", emulator_resources["AWS_S3_VECTOR_BUCKET"])
    monkeypatch.setattr(settings, "aws_kms_key_id", emulator_resources["AWS_KMS_KEY_ID"])
    monkeypatch.setattr(settings, "aws_dynamodb_table", emulator_resources["AWS_DYNAMODB_TABLE"])

    job_alpha = create_ingestion_job("file", "alpha-policy.txt", "tenant-alpha", "alpha-kb")
    await process_ingestion_job(
        job_alpha,
        content_override=(
            "Alpha Sovereign Reserve Requirement: Tier-1 liquidity buffers must remain above 24 percent "
            "across all Nairobi settlement windows.\n\n"
            "Alpha Audit Retention: Signed evidence records are archived for seven years."
        ),
    )
    status_alpha = get_job_status(job_alpha, "tenant-alpha")
    assert status_alpha is not None and status_alpha["status"] == "completed"
    assert status_alpha["chunks_processed"] == 2

    job_beta = create_ingestion_job("file", "beta-manual.txt", "tenant-beta", "beta-kb")
    await process_ingestion_job(
        job_beta,
        content_override=(
            "Beta Geothermal Telemetry Guide: Steam turbine pressure sensors report every 500 milliseconds "
            "from Olkaria station."
        ),
    )
    status_beta = get_job_status(job_beta, "tenant-beta")
    assert status_beta is not None and status_beta["status"] == "completed"

    retriever = HybridRetriever()
    alpha_hits = await retriever.retrieve("Nairobi liquidity buffer percentage", top_k=3, tenant_id="tenant-alpha")
    assert alpha_hits, "Expected live S3 Vectors hits for tenant-alpha"
    assert all(doc.metadata.get("source") == "aws-s3-vectors" for doc in alpha_hits)
    assert all(doc.metadata.get("tenant_id") == "tenant-alpha" for doc in alpha_hits)
    assert "24 percent" in alpha_hits[0].content
    assert all("Olkaria" not in doc.content for doc in alpha_hits)

    # Tenant Beta querying Alpha's terms must NEVER receive Alpha's documents
    beta_hits = await retriever.retrieve("Nairobi liquidity buffer percentage", top_k=3, tenant_id="tenant-beta")
    assert all(doc.metadata.get("tenant_id") == "tenant-beta" for doc in beta_hits)
    assert all("24 percent" not in doc.content for doc in beta_hits)

    # Deleting Alpha's collection removes its S3 objects + S3 Vectors and invalidates cached answers
    alpha_col_id = str(status_alpha["collection_id"])
    await semantic_cache.set("tenant-alpha", "Nairobi liquidity buffer percentage", "cached 24 percent", alpha_hits)
    assert await delete_collection_async(alpha_col_id, "tenant-beta") is False
    assert await delete_collection_async(alpha_col_id, "tenant-alpha") is True
    assert await semantic_cache.get("tenant-alpha", "Nairobi liquidity buffer percentage") is None

    alpha_after_delete = await S3VectorKnowledgeStore(kms_cipher=KMSEnvelopeCipher()).query(
        "tenant-alpha", "Nairobi liquidity buffer percentage", top_k=3
    )
    assert all(doc.metadata.get("collection_id") != alpha_col_id for doc in alpha_after_delete)

    # Assert directly against raw S3 Vectors index (via asyncio.to_thread) so missing S3 objects
    # cannot mask leftover vectors and the event loop is never blocked.
    s3v_client = AWSClientFactory().get_client("s3vectors")
    query_vec = deterministic_embed("Nairobi liquidity buffer percentage", 64)
    raw_resp = await asyncio.to_thread(
        s3v_client.query_vectors,
        vectorBucketName=emulator_resources["AWS_S3_VECTOR_BUCKET"],
        indexName="tenant-tenant-alpha",
        queryVector={"float32": query_vec},
        topK=10,
        returnMetadata=True,
    )
    raw_after_delete = raw_resp.get("vectors", [])
    assert all(
        (vec.get("metadata") or {}).get("collection_id") != alpha_col_id
        for vec in raw_after_delete
        if isinstance(vec, dict)
    )


@pytest.mark.asyncio
async def test_sqs_native_dlq_redrive(emulator_resources: Dict[str, str]) -> None:
    """Poison job left unacknowledged past VisibilityTimeout + maxReceiveCount redrives to DLQ."""
    factory = AWSClientFactory()
    sqs_client = factory.get_client("sqs")
    suffix = uuid.uuid4().hex[:6]

    dlq_url = str(sqs_client.create_queue(QueueName=f"test-dlq-{suffix}")["QueueUrl"])
    dlq_arn = str(
        sqs_client.get_queue_attributes(QueueUrl=dlq_url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
    )
    main_url = str(
        sqs_client.create_queue(
            QueueName=f"test-main-{suffix}",
            Attributes={
                "VisibilityTimeout": "1",
                "RedrivePolicy": json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "1"}),
            },
        )["QueueUrl"]
    )

    queue = SQSIngestionQueue(factory=factory, queue_url=main_url)
    msg_id = await queue.enqueue_job({"job_id": "poison-job-1", "tenant_id": "tenant-alpha"})
    assert msg_id

    first_attempt = await queue.receive_jobs(max_messages=1, wait_seconds=2)
    assert len(first_attempt) == 1
    assert first_attempt[0].body["job_id"] == "poison-job-1"

    # Simulate worker crash without calling acknowledge(); let visibility expire and trigger redrive
    await asyncio.sleep(1.3)
    second_attempt = await queue.receive_jobs(max_messages=1, wait_seconds=1)
    assert second_attempt == []

    dlq_messages = await queue.receive_jobs(max_messages=1, wait_seconds=2, queue_url=dlq_url)
    assert len(dlq_messages) == 1
    assert dlq_messages[0].body["job_id"] == "poison-job-1"


@pytest.mark.asyncio
async def test_dynamodb_durable_feedback_isolation(
    emulator_resources: Dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FeedbackTracker writes durably to DynamoDB with strict tenant partition isolation."""
    monkeypatch.setattr(settings, "aws_backend_enabled", True)
    monkeypatch.setattr(settings, "aws_dynamodb_table", emulator_resources["AWS_DYNAMODB_TABLE"])

    fb_alpha = await feedback_tracker.log_user_feedback(
        session_id="sess-1",
        rating="thumbs_up",
        comment="grounded citation",
        tenant_id="tenant-alpha",
    )
    fb_beta = await feedback_tracker.log_user_feedback(
        session_id="sess-1",
        rating="thumbs_down",
        comment="beta only",
        tenant_id="tenant-beta",
    )
    assert fb_alpha and fb_beta

    repo = DynamoDBStateRepository(factory=AWSClientFactory(), table_name=emulator_resources["AWS_DYNAMODB_TABLE"])
    alpha_rows = await repo.list_feedback("tenant-alpha", "sess-1")
    beta_rows = await repo.list_feedback("tenant-beta", "sess-1")
    assert len(alpha_rows) >= 1 and all(r["tenant_id"] == "tenant-alpha" for r in alpha_rows)
    assert all(r["comment"] != "beta only" for r in alpha_rows)
    assert len(beta_rows) >= 1 and all(r["tenant_id"] == "tenant-beta" for r in beta_rows)


@pytest.mark.asyncio
async def test_cloudwatch_and_xray_live_span_emission(
    emulator_resources: Dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tracer emits real CloudWatch Metrics, CloudWatch Logs, and X-Ray segments."""
    monkeypatch.setattr(settings, "aws_backend_enabled", True)
    monkeypatch.setattr(settings, "aws_cloudwatch_log_group", emulator_resources["AWS_CLOUDWATCH_LOG_GROUP"])
    monkeypatch.setattr(settings, "aws_cloudwatch_namespace", "ProductionAI/LiveTest")

    token = current_user_context.set(
        {"username": "admin", "role": "admin", "tenant_id": "tenant-alpha", "app_env": "test"}
    )
    try:
        async with tracer.span("AWSIntegrationSpan", attributes={"route": "rag"}) as span:
            span.set_attribute("cache_hit", False)
    finally:
        current_user_context.reset(token)

    factory = AWSClientFactory()
    cw = factory.get_client("cloudwatch")
    metrics = cw.list_metrics(Namespace="ProductionAI/LiveTest")["Metrics"]
    assert any(m["MetricName"] == "SpanDurationMs" for m in metrics)

    logs = factory.get_client("logs")
    events = logs.get_log_events(
        logGroupName=emulator_resources["AWS_CLOUDWATCH_LOG_GROUP"],
        logStreamName="app-runtime",
    )["events"]
    assert any("AWSIntegrationSpan" in str(e.get("message", "")) for e in events)

    # Verify direct sink succeeds AND X-Ray accepted the segment (UnprocessedTraceSegments == [])
    sink = AWSObservabilitySink(
        factory=factory,
        namespace="ProductionAI/LiveTest",
        log_group=emulator_resources["AWS_CLOUDWATCH_LOG_GROUP"],
    )
    trace_id = await sink.emit_span("DirectSinkCheck", 4.2, {"tenant.id": "tenant-alpha"}, time.time() - 0.01)
    assert trace_id is not None and trace_id.startswith("1-")

    # Direct raw X-Ray verification: prove UnprocessedTraceSegments is empty on accepted segment
    xray = factory.get_client("xray")
    raw_resp = xray.put_trace_segments(
        TraceSegmentDocuments=[
            json.dumps(
                {
                    "name": "DirectXRayVerify",
                    "id": uuid.uuid4().hex[:16],
                    "trace_id": f"1-{int(time.time()):08x}-{uuid.uuid4().hex[:24]}",
                    "start_time": time.time() - 0.02,
                    "end_time": time.time(),
                }
            )
        ]
    )
    assert raw_resp.get("UnprocessedTraceSegments", []) == []


@pytest.mark.asyncio
async def test_sqs_worker_end_to_end_staged_ingestion_and_ack(
    emulator_resources: Dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SQSIngestionWorker processes cross-replica jobs idempotently, persists DynamoDB state, and truly acks SQS."""
    from app.services.ingestion_service import (
        ACTIVE_COLLECTIONS,
        INGESTION_JOBS,
        create_ingestion_job_async,
        get_job_status_async,
        list_collections_async,
    )
    from app.services.ingestion_worker import SQSIngestionWorker
    from app.services.semantic_cache import SemanticCache

    monkeypatch.setattr(settings, "aws_backend_enabled", True)
    monkeypatch.setattr(settings, "aws_s3_bucket", emulator_resources["AWS_S3_BUCKET"])
    monkeypatch.setattr(settings, "aws_s3_vector_bucket", emulator_resources["AWS_S3_VECTOR_BUCKET"])
    monkeypatch.setattr(settings, "aws_kms_key_id", emulator_resources["AWS_KMS_KEY_ID"])
    monkeypatch.setattr(settings, "aws_dynamodb_table", emulator_resources["AWS_DYNAMODB_TABLE"])
    monkeypatch.setattr(settings, "aws_sqs_queue_url", emulator_resources["AWS_SQS_QUEUE_URL"])

    factory = AWSClientFactory()
    cipher = KMSEnvelopeCipher(factory=factory, key_id=emulator_resources["AWS_KMS_KEY_ID"])
    store = S3VectorKnowledgeStore(
        factory=factory,
        bucket_name=emulator_resources["AWS_S3_BUCKET"],
        vector_bucket_name=emulator_resources["AWS_S3_VECTOR_BUCKET"],
        kms_cipher=cipher,
    )
    queue = SQSIngestionQueue(factory=factory, queue_url=emulator_resources["AWS_SQS_QUEUE_URL"])
    state_repo = DynamoDBStateRepository(factory=factory, table_name=emulator_resources["AWS_DYNAMODB_TABLE"])
    worker = SQSIngestionWorker(queue=queue, vector_store=store, kms_cipher=cipher, state_repo=state_repo)

    # Replica A caches a pre-upload answer and enqueues the staged job
    replica_a_cache = SemanticCache()
    await replica_a_cache.set("tenant-sqs", "Kilindini container dwell times", "No report on file", [])
    assert await replica_a_cache.get("tenant-sqs", "Kilindini container dwell times") is not None

    job_id = await create_ingestion_job_async("file", "sqs-staged.txt", "tenant-sqs", "sqs-kb")
    staging_key = await store.stage_ingestion_text(
        "tenant-sqs",
        job_id,
        "SQS Consumer Proof: Kilindini port container dwell times dropped by 18 percent after automation.",
    )
    payload = {
        "job_id": job_id,
        "tenant_id": "tenant-sqs",
        "source_type": "file",
        "uri": "sqs-staged.txt",
        "collection_name": "sqs-kb",
        "staging_s3_key": staging_key,
    }
    await queue.enqueue_job(payload)

    # Simulate Replica B executing the job with empty in-memory state
    INGESTION_JOBS.pop(job_id, None)
    processed = await worker.process_once(max_messages=1, wait_seconds=2)
    assert processed == 1

    # Simulate Replica A polling status & collections with no local in-memory state
    INGESTION_JOBS.pop(job_id, None)
    ACTIVE_COLLECTIONS.clear()
    job_status = await get_job_status_async(job_id, "tenant-sqs")
    assert job_status is not None and job_status["status"] == "completed"
    cols = await list_collections_async("tenant-sqs")
    assert len(cols) == 1 and cols[0]["id"] == job_status["collection_id"]

    # Replica A's cache MUST observe DynamoDB generation bump immediately
    assert await replica_a_cache.get("tenant-sqs", "Kilindini container dwell times") is None

    # Prove message was genuinely deleted (both visible AND in-flight not-visible counts are zero)
    sqs_client = factory.get_client("sqs")
    attrs = await asyncio.to_thread(
        sqs_client.get_queue_attributes,
        QueueUrl=emulator_resources["AWS_SQS_QUEUE_URL"],
        AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"],
    )
    assert attrs["Attributes"]["ApproximateNumberOfMessages"] == "0"
    assert attrs["Attributes"]["ApproximateNumberOfMessagesNotVisible"] == "0"

    # Simulate SQS duplicate redelivery after staging cleanup: must NOT fail or duplicate collection
    await queue.enqueue_job(payload)
    assert await worker.process_once(max_messages=1, wait_seconds=2) == 1
    assert len(await list_collections_async("tenant-sqs")) == 1

    hits = await store.query("tenant-sqs", "Kilindini container dwell times", top_k=2)
    assert hits and "18 percent" in hits[0].content


@pytest.mark.asyncio
async def test_s3_vector_store_direct_roundtrip_without_kms(emulator_resources: Dict[str, str]) -> None:
    """Verify S3VectorKnowledgeStore also supports plaintext mode when KMS key is omitted."""
    store = S3VectorKnowledgeStore(
        factory=AWSClientFactory(),
        bucket_name=emulator_resources["AWS_S3_BUCKET"],
        vector_bucket_name=emulator_resources["AWS_S3_VECTOR_BUCKET"],
        kms_cipher=None,
    )
    count = await store.index_chunks(
        tenant_id="tenant-plain",
        collection_id="col-plain",
        source_uri="plain://doc",
        chunks=["FastAPI async workers use asyncio.to_thread for blocking boto3 calls."],
    )
    assert count == 1
    results = await store.query("tenant-plain", "asyncio.to_thread boto3", top_k=1)
    assert len(results) == 1
    assert "asyncio.to_thread" in results[0].content
