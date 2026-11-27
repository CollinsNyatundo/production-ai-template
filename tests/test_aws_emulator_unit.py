"""Offline unit tests for app.cloud adapters (no live AWS Emulator required)."""

from __future__ import annotations

import base64
import json
import os
from typing import Dict, List
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from app.cloud.client import AWSClientFactory
from app.cloud.queue_store import DynamoDBStateRepository, SQSIngestionQueue
from app.cloud.secrets import AWSSecretsProvider, KMSEnvelopeCipher
from app.cloud.telemetry import AWSObservabilitySink
from app.cloud.vector_store import S3VectorKnowledgeStore, deterministic_embed, sanitize_index_name
from app.config import _INSECURE_DEFAULT_JWT_SECRET, Settings, settings
from scripts.bootstrap_aws_emulator import bootstrap_aws_resources


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": f"simulated {code}"}}, "TestOp")


def test_sanitize_index_name_normalizes_tenants() -> None:
    assert sanitize_index_name("Tenant_Alpha.01!") == "tenant-tenant-alpha-01"
    assert sanitize_index_name("   ") == "tenant-default"
    assert len(sanitize_index_name("x" * 100)) <= 63


def test_deterministic_embed_cosine_ordering() -> None:
    v_rag_1 = deterministic_embed("retrieval augmented generation vector search")
    v_rag_2 = deterministic_embed("vector search with retrieval augmented generation")
    v_unrelated = deterministic_embed("banana smoothie recipe kitchen blender")

    assert len(v_rag_1) == 64
    sim_close = sum(a * b for a, b in zip(v_rag_1, v_rag_2))
    sim_far = sum(a * b for a, b in zip(v_rag_1, v_unrelated))
    assert sim_close > 0.85
    assert sim_close > sim_far

    with pytest.raises(ValueError, match="positive"):
        deterministic_embed("test", dimension=0)


def test_client_factory_caches_resets_and_honors_default_region(monkeypatch: pytest.MonkeyPatch) -> None:
    created: List[str] = []

    def fake_boto3_client(service_name: str, **kwargs: object) -> MagicMock:
        created.append(service_name)
        return MagicMock(name=f"client-{service_name}", kwargs=kwargs)

    monkeypatch.setattr("app.cloud.client.boto3.client", fake_boto3_client)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")

    default_factory = AWSClientFactory()
    assert default_factory.region_name == "eu-west-1"

    factory = AWSClientFactory(region_name="us-east-1", endpoint_url="https://127.0.0.1:9297", ca_bundle="/tmp/ca.pem")
    c1 = factory.get_client("s3")
    c2 = factory.get_client("s3")
    assert c1 is c2
    assert created == ["s3"]

    factory.reset()
    factory.get_client("s3")
    assert created == ["s3", "s3"]


def test_production_settings_guard_for_aws_vs_local_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    # AWS mode permits unused local JWT_SECRET as long as AWS_JWT_SECRET_NAME is set
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AWS_BACKEND_ENABLED", "true")
    monkeypatch.setenv("AWS_JWT_SECRET_NAME", "prod/jwt")
    monkeypatch.setenv("JWT_SECRET", _INSECURE_DEFAULT_JWT_SECRET)
    aws_settings = Settings()
    assert aws_settings.aws_jwt_secret_name == "prod/jwt"

    # AWS mode rejects empty AWS_JWT_SECRET_NAME in production
    monkeypatch.setenv("AWS_JWT_SECRET_NAME", "   ")
    with pytest.raises(ValueError, match="AWS_JWT_SECRET_NAME"):
        Settings()

    # Local mode still rejects default JWT_SECRET in production
    monkeypatch.setenv("AWS_BACKEND_ENABLED", "false")
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings()


@pytest.mark.asyncio
async def test_secrets_provider_caches_parses_and_rejects_default_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
    sm = MagicMock()
    sm.get_secret_value.return_value = {"SecretString": json.dumps({"JWT_SECRET": "rotated-key"})}
    factory = MagicMock(spec=AWSClientFactory)
    factory.get_client.return_value = sm

    provider = AWSSecretsProvider(factory=factory, ttl_seconds=60.0)
    first = await provider.get_secret("prod/jwt", json_key="JWT_SECRET")
    second = await provider.get_secret("prod/jwt", json_key="JWT_SECRET")
    assert first == "rotated-key"
    assert second == "rotated-key"
    assert sm.get_secret_value.call_count == 1

    provider.clear_cache()
    with pytest.raises(KeyError):
        await provider.get_secret("prod/jwt", json_key="MISSING")

    monkeypatch.setattr(settings, "aws_backend_enabled", True)
    monkeypatch.setattr(settings, "aws_jwt_secret_name", "prod/jwt")
    # Preserve surrounding whitespace in a valid stored key
    sm.get_secret_value.return_value = {"SecretString": json.dumps({"JWT_SECRET": "  exact-key-with-spaces  "})}
    provider.clear_cache()
    assert await provider.get_jwt_secret() == "  exact-key-with-spaces  "

    provider.clear_cache()
    sm.get_secret_value.return_value = {"SecretString": json.dumps({"JWT_SECRET": _INSECURE_DEFAULT_JWT_SECRET})}
    with pytest.raises(ValueError, match="insecure published default"):
        await provider.get_jwt_secret()


@pytest.mark.asyncio
async def test_semantic_cache_generation_blocks_stale_writes_and_auth_keeps_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException

    from app.models import QueryRequest
    from app.security.auth import create_access_token, get_current_user
    from app.services.rag_pipeline import RAGPipeline
    from app.services.semantic_cache import semantic_cache

    # End-to-end RAGPipeline.execute check: invalidation during an in-flight query
    # must prevent stale answers/sources from repopulating semantic_cache.
    tenant = "tenant-race-check"
    query = "What is the retention policy?"
    await semantic_cache.invalidate_tenant(tenant)

    async def _rewriter_with_concurrent_delete(q: str, history: str) -> str:
        await semantic_cache.invalidate_tenant(tenant)
        return q

    async def _direct_route(_q: str) -> str:
        return "direct_response"

    async def _direct_answer(_q: str) -> tuple[str, list[dict[str, object]], dict[str, int]]:
        return (
            "Stale handbook answer",
            [{"turn": 1, "thought": "direct", "tool": None, "arguments": {}, "observation": ""}],
            {"prompt_tokens": 5, "completion_tokens": 5},
        )

    async def _noop_async(*_args: object, **_kwargs: object) -> object:
        return []

    async def _safe_input(_q: str) -> tuple[bool, str]:
        return True, ""

    async def _identity_output(text: str) -> str:
        return text

    async def _zero_cost(**_kwargs: object) -> dict[str, float]:
        return {"total_cost": 0.0}

    monkeypatch.setattr("app.services.rag_pipeline.input_guard.validate", _safe_input)
    monkeypatch.setattr("app.services.rag_pipeline.conversation_service.get_history", _noop_async)
    monkeypatch.setattr("app.services.rag_pipeline.conversation_service.add_message", _noop_async)
    monkeypatch.setattr("app.services.rag_pipeline.query_rewriter.rewrite", _rewriter_with_concurrent_delete)
    monkeypatch.setattr("app.services.rag_pipeline.adaptive_router.route_adaptively", _direct_route)
    monkeypatch.setattr(RAGPipeline, "_direct_response", lambda _self, q: _direct_answer(q))
    monkeypatch.setattr("app.services.rag_pipeline.cost_tracker.track_usage", _zero_cost)
    monkeypatch.setattr("app.services.rag_pipeline.output_filter.sanitize", _identity_output)
    monkeypatch.setattr("app.services.rag_pipeline.memory_manager.trigger_async_extraction", lambda **_kw: None)
    monkeypatch.setattr("app.services.rag_pipeline.trajectory_logger.log_run", _noop_async)

    pipeline = RAGPipeline()
    await pipeline.execute(
        QueryRequest(query=query, session_id="sess-race", tenant_id=tenant, user_id="admin", use_cache=True)
    )
    assert await semantic_cache.get(tenant, query) is None

    # Explicitly run in local-secret mode so signature verification succeeds and
    # the unknown-user 401 path (not signature mismatch) is exercised.
    monkeypatch.setattr(settings, "aws_backend_enabled", False)
    unknown_token = create_access_token({"sub": "nonexistent-user"})
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token=unknown_token, api_key=None)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "User profile not found."


@pytest.mark.asyncio
async def test_s3_delete_objects_partial_errors_preserve_collection_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.ingestion_service import ACTIVE_COLLECTIONS, delete_collection_async
    from app.services.semantic_cache import semantic_cache

    s3 = MagicMock()
    s3.list_objects_v2.return_value = {
        "Contents": [{"Key": "tenants/tenant-a/collections/col-err/chunk-0000.txt"}],
        "IsTruncated": False,
    }
    # Simulate AWS S3 HTTP 200 response with per-object Errors under Quiet=True
    s3.delete_objects.return_value = {
        "Errors": [
            {
                "Key": "tenants/tenant-a/collections/col-err/chunk-0000.txt",
                "Code": "AccessDenied",
                "Message": "Access Denied",
            }
        ]
    }
    s3v = MagicMock()
    factory = MagicMock(spec=AWSClientFactory)
    factory.get_client.side_effect = lambda name: s3 if name == "s3" else s3v

    store = S3VectorKnowledgeStore(factory=factory, bucket_name="docs", vector_bucket_name="vecs")
    with pytest.raises(RuntimeError, match="AccessDenied"):
        await store.delete_collection_chunks("tenant-a", "col-err")

    # Verify delete_collection_async propagates the error, keeps ACTIVE_COLLECTIONS intact,
    # AND still invalidates cached answers because vectors were already removed.
    monkeypatch.setattr(settings, "aws_backend_enabled", True)
    monkeypatch.setattr(settings, "aws_dynamodb_table", "")
    monkeypatch.setattr("app.services.ingestion_service.S3VectorKnowledgeStore", lambda **_kw: store)
    await semantic_cache.set("tenant-a", "err-cache-query", "stale answer", [])
    ACTIVE_COLLECTIONS["col-err"] = {"id": "col-err", "tenant_id": "tenant-a", "chunk_count": 1}
    try:
        with pytest.raises(RuntimeError, match="AccessDenied"):
            await delete_collection_async("col-err", "tenant-a")
        assert "col-err" in ACTIVE_COLLECTIONS
        assert await semantic_cache.get("tenant-a", "err-cache-query") is None
    finally:
        ACTIVE_COLLECTIONS.pop("col-err", None)


@pytest.mark.asyncio
async def test_sqs_ingestion_worker_acknowledges_success_retries_and_deduplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.cloud.queue_store import QueuedMessage
    from app.services.ingestion_service import INGESTION_JOBS
    from app.services.ingestion_worker import SQSIngestionWorker

    monkeypatch.setattr(settings, "aws_backend_enabled", False)
    staged_objects: dict[str, bytes] = {
        "staging/tenant-a/job-ok.txt": b"Staged paragraph content exceeding twenty chars.",
        "staging/tenant-a/job-ack-err.txt": b"Staged paragraph content exceeding twenty chars.",
        "staging/tenant-a/job-fail.txt": b"Staged paragraph content exceeding twenty chars.",
        "staging/tenant-a/job-fail-up.txt": b"Staged paragraph content exceeding twenty chars.",
    }
    s3 = MagicMock()

    def _s3_get_object(Bucket: str, Key: str) -> dict[str, object]:
        if Key not in staged_objects:
            raise _client_error("NoSuchKey")
        payload = staged_objects[Key]
        return {"Body": MagicMock(read=lambda p=payload: p), "Metadata": {"kms_encrypted": "false"}}

    def _s3_delete_objects(Bucket: str, Delete: dict[str, list[dict[str, str]]]) -> dict[str, object]:
        for obj in Delete.get("Objects", []):
            staged_objects.pop(str(obj["Key"]), None)
        return {}

    s3.get_object.side_effect = _s3_get_object
    s3.delete_objects.side_effect = _s3_delete_objects
    s3v = MagicMock()
    sqs = MagicMock()
    sqs.get_queue_attributes.return_value = {
        "Attributes": {"RedrivePolicy": json.dumps({"deadLetterTargetArn": "arn:dlq", "maxReceiveCount": "3"})}
    }
    factory = MagicMock(spec=AWSClientFactory)
    factory.get_client.side_effect = lambda name: {"s3": s3, "s3vectors": s3v, "sqs": sqs}[name]

    queue = SQSIngestionQueue(factory=factory, queue_url="https://127.0.0.1:9297/000000000000/ingest")
    store = S3VectorKnowledgeStore(factory=factory, bucket_name="docs", vector_bucket_name="vecs", kms_cipher=None)
    worker = SQSIngestionWorker(queue=queue, vector_store=store)

    call_count = 0

    async def _complete_job(
        job_id: str,
        content_override: str | None = None,
        *,
        failure_status: str = "failed",
        reconcile_existing: bool = False,
        raise_on_error: bool = False,
    ) -> None:
        nonlocal call_count
        call_count += 1
        assert content_override == "Staged paragraph content exceeding twenty chars."
        INGESTION_JOBS[job_id]["status"] = "completed"

    monkeypatch.setattr("app.services.ingestion_worker.process_ingestion_job", _complete_job)
    ok_msg = QueuedMessage(
        message_id="m-ok",
        receipt_handle="rh-ok",
        body={
            "job_id": "job-ok",
            "tenant_id": "tenant-a",
            "source_type": "file",
            "uri": "doc.txt",
            "collection_name": "doc-kb",
            "staging_s3_key": "staging/tenant-a/job-ok.txt",
        },
        receive_count=1,
    )
    assert await worker.process_message(ok_msg) is True
    sqs.delete_message.assert_called_once_with(
        QueueUrl="https://127.0.0.1:9297/000000000000/ingest",
        ReceiptHandle="rh-ok",
    )
    s3.delete_objects.assert_called_once()

    # Duplicate SQS delivery after completion skips re-indexing and acks immediately
    sqs.delete_message.reset_mock()
    assert await worker.process_message(ok_msg) is True
    assert call_count == 1
    sqs.delete_message.assert_called_once()

    # SQS acknowledgement error after durable completion MUST NOT overwrite "completed" state;
    # redelivery deduplicates without re-indexing and succeeds on ack retry.
    sqs.delete_message.reset_mock()
    sqs.delete_message.side_effect = [_client_error("AccessDenied"), None]
    ack_err_msg = QueuedMessage(
        message_id="m-ack-err",
        receipt_handle="rh-ack-err-1",
        body={
            "job_id": "job-ack-err",
            "tenant_id": "tenant-a",
            "source_type": "file",
            "uri": "ack.txt",
            "collection_name": "ack-kb",
            "staging_s3_key": "staging/tenant-a/job-ack-err.txt",
        },
        receive_count=1,
    )
    assert await worker.process_message(ack_err_msg) is False
    assert INGESTION_JOBS["job-ack-err"]["status"] == "completed"
    assert call_count == 2
    assert "staging/tenant-a/job-ack-err.txt" in staged_objects
    ack_retry_msg = QueuedMessage(
        message_id="m-ack-err",
        receipt_handle="rh-ack-err-2",
        body=ack_err_msg.body,
        receive_count=2,
    )
    assert await worker.process_message(ack_retry_msg) is True
    assert call_count == 2  # Deduplicated without re-indexing!
    assert "staging/tenant-a/job-ack-err.txt" not in staged_objects
    sqs.delete_message.side_effect = None

    # Non-terminal failure (receive_count=1 < 3) records "retrying" and preserves staging object
    sqs.delete_message.reset_mock()
    s3.delete_objects.reset_mock()

    async def _fail_job(
        job_id: str,
        content_override: str | None = None,
        *,
        failure_status: str = "failed",
        reconcile_existing: bool = False,
        raise_on_error: bool = False,
    ) -> None:
        if raise_on_error:
            raise RuntimeError("simulated indexing error")
        INGESTION_JOBS[job_id]["status"] = failure_status
        INGESTION_JOBS[job_id]["error"] = "simulated indexing error"

    monkeypatch.setattr("app.services.ingestion_worker.process_ingestion_job", _fail_job)
    retry_msg = QueuedMessage(
        message_id="m-fail-1",
        receipt_handle="rh-fail-1",
        body={
            "job_id": "job-fail",
            "tenant_id": "tenant-a",
            "source_type": "file",
            "uri": "bad.txt",
            "collection_name": "bad-kb",
            "staging_s3_key": "staging/tenant-a/job-fail.txt",
        },
        receive_count=1,
    )
    assert await worker.process_message(retry_msg) is False
    assert INGESTION_JOBS["job-fail"]["status"] == "retrying"
    assert "staging/tenant-a/job-fail.txt" in staged_objects
    sqs.delete_message.assert_not_called()

    # Live queue policy reconciliation DOWN (3 -> 2) on the SAME running worker:
    # attempt 2 is now terminal -> marks "failed" and deletes staged upload.
    sqs.get_queue_attributes.return_value = {
        "Attributes": {"RedrivePolicy": json.dumps({"deadLetterTargetArn": "arn:dlq", "maxReceiveCount": "2"})}
    }
    second_msg = QueuedMessage(
        message_id="m-fail-2",
        receipt_handle="rh-fail-2",
        body=retry_msg.body,
        receive_count=2,
    )
    assert await worker.process_message(second_msg) is False
    assert INGESTION_JOBS["job-fail"]["status"] == "failed"
    assert "staging/tenant-a/job-fail.txt" not in staged_objects
    sqs.delete_message.assert_not_called()

    # Live queue policy reconciliation UP (2 -> 3) on the SAME running worker using a fresh job
    # whose staging file genuinely exists: attempt 2 preserves staging and attempt 3 succeeds!
    sqs.get_queue_attributes.return_value = {
        "Attributes": {"RedrivePolicy": json.dumps({"deadLetterTargetArn": "arn:dlq", "maxReceiveCount": "3"})}
    }
    up_msg_2 = QueuedMessage(
        message_id="m-up-2",
        receipt_handle="rh-up-2",
        body={
            "job_id": "job-fail-up",
            "tenant_id": "tenant-a",
            "source_type": "file",
            "uri": "up.txt",
            "collection_name": "up-kb",
            "staging_s3_key": "staging/tenant-a/job-fail-up.txt",
        },
        receive_count=2,
    )
    assert await worker.process_message(up_msg_2) is False
    assert INGESTION_JOBS["job-fail-up"]["status"] == "retrying"
    assert "staging/tenant-a/job-fail-up.txt" in staged_objects

    # Attempt 3 loads the preserved staged file and completes cleanly
    monkeypatch.setattr("app.services.ingestion_worker.process_ingestion_job", _complete_job)
    up_msg_3 = QueuedMessage(
        message_id="m-up-3",
        receipt_handle="rh-up-3",
        body=up_msg_2.body,
        receive_count=3,
    )
    assert await worker.process_message(up_msg_3) is True
    assert INGESTION_JOBS["job-fail-up"]["status"] == "completed"
    assert "staging/tenant-a/job-fail-up.txt" not in staged_objects

    # Worker refuses to poll SQS when RedrivePolicy is unreadable (no messages dequeued)
    sqs.receive_message.reset_mock()
    sqs.get_queue_attributes.side_effect = _client_error("AccessDenied")
    with pytest.raises(RuntimeError, match="RedrivePolicy is missing or unreadable"):
        await worker.process_once()
    sqs.receive_message.assert_not_called()
    sqs.get_queue_attributes.side_effect = None


@pytest.mark.asyncio
async def test_ingest_routes_return_503_when_sqs_redrive_policy_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from io import BytesIO

    from fastapi import BackgroundTasks, HTTPException, UploadFile

    from app.api.ingest import IngestRequest, start_file_ingestion, start_ingestion
    from app.security.auth import User
    from app.services.ingestion_service import INGESTION_JOBS

    monkeypatch.setattr(settings, "aws_backend_enabled", True)
    monkeypatch.setattr(settings, "aws_sqs_queue_url", "https://127.0.0.1:9297/0/q")

    async def _unreadable_policy() -> int | None:
        return None

    stage_mock = MagicMock()
    monkeypatch.setattr("app.api.ingest.sqs_ingestion_queue.get_max_receive_count", _unreadable_policy)
    monkeypatch.setattr("app.api.ingest.S3VectorKnowledgeStore", stage_mock)

    user = User(username="u1", tenant_id="tenant-unready", scopes=["read", "write"])
    before_jobs = set(INGESTION_JOBS.keys())

    with pytest.raises(HTTPException) as exc_web:
        await start_ingestion(
            BackgroundTasks(),
            IngestRequest(source_type="web", uri="https://example.com/doc"),
            current_user=user,
        )
    assert exc_web.value.status_code == 503

    upload = UploadFile(filename="doc.txt", file=BytesIO(b"hello world content"))
    with pytest.raises(HTTPException) as exc_file:
        await start_file_ingestion(
            BackgroundTasks(),
            file=upload,
            collection_name="col-unready",
            current_user=user,
        )
    assert exc_file.value.status_code == 503

    # Neither route created a job or touched S3 staging
    assert set(INGESTION_JOBS.keys()) == before_jobs
    stage_mock.assert_not_called()

    # Transport failures (e.g. EndpointConnectionError) also return structured HTTP 503
    from botocore.exceptions import EndpointConnectionError

    async def _unreachable_sqs() -> int | None:
        raise EndpointConnectionError(endpoint_url="https://127.0.0.1:9297")

    monkeypatch.setattr("app.api.ingest.sqs_ingestion_queue.get_max_receive_count", _unreachable_sqs)
    with pytest.raises(HTTPException) as exc_web_conn:
        await start_ingestion(
            BackgroundTasks(),
            IngestRequest(source_type="web", uri="https://example.com/doc2"),
            current_user=user,
        )
    assert exc_web_conn.value.status_code == 503

    upload2 = UploadFile(filename="doc2.txt", file=BytesIO(b"hello world content"))
    with pytest.raises(HTTPException) as exc_file_conn:
        await start_file_ingestion(
            BackgroundTasks(),
            file=upload2,
            collection_name="col-unready-2",
            current_user=user,
        )
    assert exc_file_conn.value.status_code == 503
    assert set(INGESTION_JOBS.keys()) == before_jobs
    stage_mock.assert_not_called()


@pytest.mark.asyncio
async def test_load_staged_text_follows_object_kms_metadata_across_config_changes() -> None:
    dek = os.urandom(32)
    kms = MagicMock()
    kms.generate_data_key.return_value = {"Plaintext": dek, "CiphertextBlob": b"wrapped-dek"}
    kms.decrypt.return_value = {"Plaintext": dek}

    s3 = MagicMock()
    factory = MagicMock(spec=AWSClientFactory)
    factory.get_client.side_effect = lambda name: kms if name == "kms" else s3

    cipher_enabled = KMSEnvelopeCipher(factory=factory, key_id="key-123")
    cipher_read_only = KMSEnvelopeCipher(factory=factory, key_id="")

    # 1. Plaintext object staged before KMS was enabled MUST NOT be decrypted when KMS is later enabled
    s3.get_object.return_value = {
        "Body": MagicMock(read=lambda: b"Plaintext upload staged before KMS."),
        "Metadata": {"kms_encrypted": "false"},
    }
    store_with_kms = S3VectorKnowledgeStore(
        factory=factory, bucket_name="docs", vector_bucket_name="vecs", kms_cipher=cipher_enabled
    )
    assert await store_with_kms.load_staged_text("tenant-a", "staging/tenant-a/j1.txt") == (
        "Plaintext upload staged before KMS."
    )

    # 2. Encrypted object staged with KMS MUST still decrypt when consumer has no write key_id
    encrypted_b64 = await cipher_enabled.encrypt_text("tenant-a", "Encrypted staged payload.")
    s3.get_object.return_value = {
        "Body": MagicMock(read=lambda: encrypted_b64.encode("utf-8")),
        "Metadata": {"kms_encrypted": "true"},
    }
    store_read_only = S3VectorKnowledgeStore(
        factory=factory, bucket_name="docs", vector_bucket_name="vecs", kms_cipher=cipher_read_only
    )
    assert await store_read_only.load_staged_text("tenant-a", "staging/tenant-a/j2.txt") == "Encrypted staged payload."

    # 3. Encrypted object MUST fail explicitly when no KMS cipher exists (never index ciphertext)
    store_no_kms = S3VectorKnowledgeStore(
        factory=factory, bucket_name="docs", vector_bucket_name="vecs", kms_cipher=None
    )
    with pytest.raises(RuntimeError, match="no KMS cipher"):
        await store_no_kms.load_staged_text("tenant-a", "staging/tenant-a/j2.txt")


@pytest.mark.asyncio
async def test_cross_replica_semantic_cache_invalidation_via_shared_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.semantic_cache import SemanticCache

    shared_gens: dict[str, int] = {}

    async def _fake_get_gen(tenant_id: str) -> int:
        return shared_gens.get(tenant_id, 0)

    async def _fake_inc_gen(tenant_id: str) -> int:
        shared_gens[tenant_id] = shared_gens.get(tenant_id, 0) + 1
        return shared_gens[tenant_id]

    monkeypatch.setattr(settings, "aws_backend_enabled", True)
    monkeypatch.setattr(settings, "aws_dynamodb_table", "shared-state")
    monkeypatch.setattr("app.services.semantic_cache.dynamodb_state_repo.get_cache_generation", _fake_get_gen)
    monkeypatch.setattr("app.services.semantic_cache.dynamodb_state_repo.increment_cache_generation", _fake_inc_gen)

    replica_a = SemanticCache()
    replica_b = SemanticCache()
    await replica_a.set("tenant-x", "policy question", "old answer", [])
    assert (await replica_a.get("tenant-x", "policy question")) is not None

    # Replica B finishes indexing and invalidates the tenant -> Replica A MUST miss immediately
    await replica_b.invalidate_tenant("tenant-x")
    assert await replica_a.get("tenant-x", "policy question") is None


@pytest.mark.asyncio
async def test_kms_envelope_cipher_handles_large_payloads_and_legacy_blobs() -> None:
    dek = os.urandom(32)
    kms = MagicMock()
    kms.generate_data_key.return_value = {"Plaintext": dek, "CiphertextBlob": b"wrapped-dek"}
    kms.decrypt.side_effect = [
        {"Plaintext": dek},
        _client_error("InvalidCiphertextException"),
        {"Plaintext": b"legacy-secret"},
    ]
    factory = MagicMock(spec=AWSClientFactory)
    factory.get_client.return_value = kms

    cipher = KMSEnvelopeCipher(factory=factory, key_id="key-123")
    large_text = "A" * 10_000  # Exceeds KMS direct 4,096-byte Encrypt limit
    enc = await cipher.encrypt_text("tenant-a", large_text)
    envelope = json.loads(base64.b64decode(enc).decode("utf-8"))
    assert envelope["v"] == 2 and envelope["alg"] == "AES-256-GCM"
    assert await cipher.decrypt_text("tenant-a", enc) == large_text

    with pytest.raises(PermissionError, match="InvalidCiphertextException"):
        await cipher.decrypt_text("tenant-b", enc)

    # Backward-compatible legacy direct KMS ciphertext blob
    legacy_b64 = base64.b64encode(b"raw-legacy-kms-blob").decode("ascii")
    assert await cipher.decrypt_text("tenant-a", legacy_b64) == "legacy-secret"


@pytest.mark.asyncio
async def test_vector_store_batches_over_500_rolls_back_on_error_and_deletes_collection() -> None:
    s3 = MagicMock()
    s3.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "tenants/tenant-a/collections/col-1/chunk-0000.txt"},
            {"Key": "tenants/tenant-a/collections/col-1/chunk-0001.txt"},
        ],
        "IsTruncated": False,
    }
    s3v = MagicMock()
    factory = MagicMock(spec=AWSClientFactory)
    factory.get_client.side_effect = lambda name: s3 if name == "s3" else s3v

    store = S3VectorKnowledgeStore(factory=factory, bucket_name="docs", vector_bucket_name="vecs")
    chunks = [f"chunk text number {i}" for i in range(550)]
    count = await store.index_chunks("tenant-a", "col-big", "file://big.txt", chunks)
    assert count == 550
    assert s3v.put_vectors.call_count == 2
    assert len(s3v.put_vectors.call_args_list[0].kwargs["vectors"]) == 500
    assert len(s3v.put_vectors.call_args_list[1].kwargs["vectors"]) == 50

    # Rollback on second batch failure cleans up already-written vectors and S3 objects
    s3v.put_vectors.reset_mock()
    s3v.put_vectors.side_effect = [None, _client_error("InternalFailure")]
    with pytest.raises(ClientError):
        await store.index_chunks("tenant-a", "col-fail", "file://fail.txt", chunks)
    s3v.delete_vectors.assert_called()
    s3.delete_objects.assert_called()

    # Explicit collection deletion removes both vectors and archived objects
    s3v.delete_vectors.reset_mock()
    s3.delete_objects.reset_mock()
    removed = await store.delete_collection_chunks("tenant-a", "col-1")
    assert removed == 2
    s3v.delete_vectors.assert_called_once_with(
        vectorBucketName="vecs",
        indexName="tenant-tenant-a",
        keys=["col-1:0000", "col-1:0001"],
    )
    s3.delete_objects.assert_called_once()


@pytest.mark.asyncio
async def test_vector_store_skips_cross_tenant_hit_and_handles_missing_index() -> None:
    s3 = MagicMock()
    s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"tenant-a-body")}
    s3v = MagicMock()
    s3v.query_vectors.return_value = {
        "vectors": [
            {
                "key": "c1:0000",
                "distance": 0.1,
                "metadata": {"tenant_id": "tenant-b", "s3_key": "tenants/tenant-b/x.txt", "kms_encrypted": False},
            },
            {
                "key": "c1:0001",
                "distance": 0.2,
                "metadata": {"tenant_id": "tenant-a", "s3_key": "tenants/tenant-a/x.txt", "kms_encrypted": False},
            },
        ]
    }
    factory = MagicMock(spec=AWSClientFactory)
    factory.get_client.side_effect = lambda name: s3 if name == "s3" else s3v

    store = S3VectorKnowledgeStore(factory=factory, bucket_name="docs", vector_bucket_name="vecs")
    docs = await store.query("tenant-a", "hello", top_k=5)
    assert len(docs) == 1
    assert docs[0].content == "tenant-a-body"
    assert docs[0].metadata["tenant_id"] == "tenant-a"
    assert abs(docs[0].score - 0.8) < 1e-6

    s3v.query_vectors.side_effect = _client_error("NotFoundException")
    assert await store.query("tenant-new", "hello") == []


@pytest.mark.asyncio
async def test_sqs_and_dynamodb_repositories() -> None:
    sqs = MagicMock()
    sqs.send_message.return_value = {"MessageId": "m-1"}
    sqs.receive_message.return_value = {
        "Messages": [{"MessageId": "m-1", "ReceiptHandle": "rh-1", "Body": json.dumps({"job_id": "j1"})}]
    }
    ddb = MagicMock()
    ddb.query.return_value = {
        "Items": [
            {
                "tenant_id": {"S": "tenant-a"},
                "item_key": {"S": "FEEDBACK#s1#fb-1"},
                "session_id": {"S": "s1"},
                "rating": {"S": "thumbs_up"},
                "comment": {"S": "accurate"},
                "created_at": {"S": "2026-11-24T00:00:00Z"},
            }
        ]
    }
    factory = MagicMock(spec=AWSClientFactory)
    factory.get_client.side_effect = lambda name: sqs if name == "sqs" else ddb

    queue = SQSIngestionQueue(factory=factory, queue_url="https://127.0.0.1:9297/000000000000/q")
    assert await queue.enqueue_job({"job_id": "j1"}) == "m-1"
    msgs = await queue.receive_jobs()
    assert len(msgs) == 1 and msgs[0].body["job_id"] == "j1"
    await queue.acknowledge("rh-1")
    sqs.delete_message.assert_called_once()

    repo = DynamoDBStateRepository(factory=factory, table_name="state")
    fb_id = await repo.put_feedback("tenant-a", "s1", "thumbs_up", "accurate")
    assert fb_id.startswith("fb-")
    rows = await repo.list_feedback("tenant-a", "s1")
    assert len(rows) == 1 and rows[0]["rating"] == "thumbs_up"

    # Extended SQS visibility and RedrivePolicy lookup
    await queue.extend_visibility("rh-1", 45)
    sqs.change_message_visibility.assert_called_once()
    sqs.get_queue_attributes.return_value = {"Attributes": {"RedrivePolicy": json.dumps({"maxReceiveCount": "4"})}}
    assert await queue.get_max_receive_count() == 4

    # DynamoDB shared ingestion jobs, leases, collections, and cache generations
    job_payload = {"job_id": "j1", "tenant_id": "tenant-a", "status": "processing"}
    await repo.put_ingestion_job("tenant-a", job_payload, lease_owner="w1", lease_expires_at=9999999999)
    ddb.get_item.return_value = {"Item": {"payload": {"S": json.dumps(job_payload)}, "status": {"S": "processing"}}}
    assert (await repo.get_ingestion_job("tenant-a", "j1")) == job_payload

    # Claim returns "acquired", then "completed", then "in_progress" on conditional failure
    ddb.get_item.return_value = {}
    assert await repo.claim_ingestion_job("tenant-a", job_payload, "w1", lease_seconds=30) == "acquired"
    ddb.get_item.return_value = {"Item": {"status": {"S": "completed"}}}
    assert await repo.claim_ingestion_job("tenant-a", job_payload, "w2", lease_seconds=30) == "completed"
    ddb.get_item.side_effect = [{}, {"Item": {"status": {"S": "processing"}}}]
    ddb.put_item.side_effect = _client_error("ConditionalCheckFailedException")
    assert await repo.claim_ingestion_job("tenant-a", job_payload, "w2", lease_seconds=30) == "in_progress"
    ddb.get_item.side_effect = None
    ddb.put_item.side_effect = None

    assert await repo.renew_ingestion_lease("tenant-a", "j1", "w1", lease_seconds=30) is True
    ddb.update_item.side_effect = _client_error("ConditionalCheckFailedException")
    assert await repo.renew_ingestion_lease("tenant-a", "j1", "w2", lease_seconds=30) is False
    ddb.update_item.side_effect = None

    col_payload = {"id": "col-j1", "tenant_id": "tenant-a", "name": "kb"}
    col_payload_2 = {"id": "col-j2", "tenant_id": "tenant-a", "name": "kb-2"}
    await repo.put_collection("tenant-a", col_payload)
    ddb.get_item.return_value = {"Item": {"payload": {"S": json.dumps(col_payload)}}}
    assert (await repo.get_collection("tenant-a", "col-j1")) == col_payload
    # Verify multi-page LastEvaluatedKey pagination collects all pages
    ddb.query.side_effect = [
        {
            "Items": [{"payload": {"S": json.dumps(col_payload)}}],
            "LastEvaluatedKey": {"tenant_id": {"S": "tenant-a"}, "item_key": {"S": "COLLECTION#col-j1"}},
        },
        {"Items": [{"payload": {"S": json.dumps(col_payload_2)}}]},
    ]
    assert (await repo.list_collections("tenant-a")) == [col_payload, col_payload_2]
    ddb.query.side_effect = None
    ddb.delete_item.return_value = {"Attributes": {"collection_id": {"S": "col-j1"}}}
    assert await repo.delete_collection("tenant-a", "col-j1") is True

    ddb.get_item.return_value = {"Item": {"generation": {"N": "7"}}}
    assert await repo.get_cache_generation("tenant-a") == 7
    ddb.update_item.return_value = {"Attributes": {"generation": {"N": "8"}}}
    assert await repo.increment_cache_generation("tenant-a") == 8


@pytest.mark.asyncio
async def test_ingestion_service_dynamodb_async_lifecycle_and_worker_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    from app.cloud.queue_store import QueuedMessage
    from app.services import ingestion_service as svc
    from app.services.ingestion_worker import SQSIngestionWorker

    jobs_db: dict[tuple[str, str], dict[str, object]] = {}
    cols_db: dict[tuple[str, str], dict[str, object]] = {}
    gen_db: dict[str, int] = {}

    class _FakeRepo:
        async def put_ingestion_job(self, tenant_id: str, job: dict[str, object], **_kw: object) -> None:
            jobs_db[(tenant_id, str(job["job_id"]))] = dict(job)

        async def get_ingestion_job(self, tenant_id: str, job_id: str) -> dict[str, object] | None:
            row = jobs_db.get((tenant_id, job_id))
            return dict(row) if row is not None else None

        async def claim_ingestion_job(
            self, tenant_id: str, job: dict[str, object], owner_id: str, lease_seconds: int = 30
        ) -> str:
            existing = jobs_db.get((tenant_id, str(job["job_id"])))
            if existing and existing.get("status") == "completed":
                return "completed"
            if existing and existing.get("lease_owner") and existing.get("lease_owner") != owner_id:
                return "in_progress"
            copy = dict(job)
            copy["lease_owner"] = owner_id
            jobs_db[(tenant_id, str(job["job_id"]))] = copy
            return "acquired"

        async def renew_ingestion_lease(self, *_args: object, **_kw: object) -> bool:
            return True

        async def put_collection(self, tenant_id: str, col: dict[str, object]) -> None:
            cols_db[(tenant_id, str(col["id"]))] = dict(col)

        async def get_collection(self, tenant_id: str, col_id: str) -> dict[str, object] | None:
            row = cols_db.get((tenant_id, col_id))
            return dict(row) if row is not None else None

        async def list_collections(self, tenant_id: str) -> list[dict[str, object]]:
            return [dict(v) for (t, _), v in cols_db.items() if t == tenant_id]

        async def delete_collection(self, tenant_id: str, col_id: str) -> bool:
            return cols_db.pop((tenant_id, col_id), None) is not None

        async def get_cache_generation(self, tenant_id: str) -> int:
            return gen_db.get(tenant_id, 0)

        async def increment_cache_generation(self, tenant_id: str) -> int:
            gen_db[tenant_id] = gen_db.get(tenant_id, 0) + 1
            return gen_db[tenant_id]

    fake_repo = _FakeRepo()
    fake_store = MagicMock()

    async def _index_chunks(**_kw: object) -> int:
        return 1

    async def _delete_chunks(**_kw: object) -> int:
        return 1

    fake_store.index_chunks = _index_chunks
    fake_store.delete_collection_chunks = _delete_chunks

    monkeypatch.setattr(settings, "aws_backend_enabled", True)
    monkeypatch.setattr(settings, "aws_dynamodb_table", "shared-table")
    monkeypatch.setattr("app.services.ingestion_service.dynamodb_state_repo", fake_repo)
    monkeypatch.setattr("app.services.semantic_cache.dynamodb_state_repo", fake_repo)
    monkeypatch.setattr("app.services.ingestion_service.S3VectorKnowledgeStore", lambda **_kw: fake_store)

    job_id = await svc.create_ingestion_job_async("file", "doc.txt", "tenant-ddb", "kb-ddb")
    await svc.process_ingestion_job(
        job_id,
        content_override="Paragraph content longer than twenty characters for indexing.",
        reconcile_existing=True,
    )
    status_row = await svc.get_job_status_async(job_id, "tenant-ddb")
    assert status_row is not None and status_row["status"] == "completed"
    cols = await svc.list_collections_async("tenant-ddb")
    assert len(cols) == 1
    assert await svc.delete_collection_async(str(cols[0]["id"]), "tenant-ddb") is True
    assert await svc.list_collections_async("tenant-ddb") == []

    # Worker shared-state claim skip (in_progress & completed) + clean run_loop shutdown
    sqs_mock = MagicMock()
    sqs_mock.receive_message.return_value = {"Messages": []}
    sqs_mock.get_queue_attributes.return_value = {"Attributes": {}}
    factory = MagicMock(spec=AWSClientFactory)
    factory.get_client.return_value = sqs_mock
    queue = SQSIngestionQueue(factory=factory, queue_url="https://127.0.0.1:9297/0/q")
    worker = SQSIngestionWorker(queue=queue, vector_store=fake_store, state_repo=fake_repo)  # type: ignore[arg-type]

    # Completed job redelivery skips reindexing and acks
    dup_msg = QueuedMessage(
        message_id="m-dup",
        receipt_handle="rh-dup",
        body={"job_id": job_id, "tenant_id": "tenant-ddb", "source_type": "file", "uri": "doc.txt"},
    )
    assert await worker.process_message(dup_msg) is True
    sqs_mock.delete_message.assert_called_once()

    # Active lease on another worker returns False without acking
    jobs_db[("tenant-ddb", "job-busy")] = {"job_id": "job-busy", "status": "processing", "lease_owner": "other-worker"}
    sqs_mock.delete_message.reset_mock()
    busy_msg = QueuedMessage(
        message_id="m-busy",
        receipt_handle="rh-busy",
        body={"job_id": "job-busy", "tenant_id": "tenant-ddb", "source_type": "file", "uri": "busy.txt"},
    )
    assert await worker.process_message(busy_msg) is False
    sqs_mock.delete_message.assert_not_called()

    stop_event = asyncio.Event()
    stop_event.set()
    await worker.run_loop(stop_event, poll_wait_seconds=1)


@pytest.mark.asyncio
async def test_observability_sink_emits_and_detects_unprocessed_xray_segments() -> None:
    clients: Dict[str, MagicMock] = {
        "cloudwatch": MagicMock(),
        "logs": MagicMock(),
        "xray": MagicMock(),
    }
    clients["xray"].put_trace_segments.return_value = {"UnprocessedTraceSegments": []}
    factory = MagicMock(spec=AWSClientFactory)
    factory.get_client.side_effect = lambda name: clients[name]

    sink = AWSObservabilitySink(factory=factory, namespace="NS", log_group="/test/lg")
    trace_id = await sink.emit_span("RAGPipeline.execute", 12.5, {"tenant.id": "tenant-a"})
    assert trace_id is not None and trace_id.startswith("1-")
    clients["cloudwatch"].put_metric_data.assert_called_once()
    clients["logs"].put_log_events.assert_called_once()
    clients["xray"].put_trace_segments.assert_called_once()

    # Non-empty UnprocessedTraceSegments fails emission instead of silently succeeding
    clients["xray"].put_trace_segments.return_value = {
        "UnprocessedTraceSegments": [{"Id": "bad-seg", "ErrorCode": "InvalidFormat"}]
    }
    assert await sink.emit_span("RAGPipeline.execute", 1.0, {}) is None

    clients["xray"].put_trace_segments.return_value = {"UnprocessedTraceSegments": []}
    clients["cloudwatch"].put_metric_data.side_effect = RuntimeError("network down")
    assert await sink.emit_span("RAGPipeline.execute", 1.0, {}) is None


def test_bootstrap_passes_location_constraint_outside_us_east_1(caplog: pytest.LogCaptureFixture) -> None:
    s3 = MagicMock()
    s3.head_bucket.side_effect = _client_error("404")
    s3.get_bucket_lifecycle_configuration.return_value = {
        "Rules": [{"ID": "existing-archive-rule", "Filter": {"Prefix": "tenants/"}, "Status": "Enabled"}]
    }
    s3v = MagicMock()
    kms = MagicMock()
    kms.list_aliases.return_value = {"Aliases": [{"AliasName": "alias/q-tenant-key", "TargetKeyId": "key-eu"}]}
    sm = MagicMock()
    sm.get_secret_value.return_value = {"SecretString": json.dumps({"JWT_SECRET": "existing-secret"})}
    sqs = MagicMock()
    sqs.create_queue.side_effect = [{"QueueUrl": "https://sqs/dlq"}, {"QueueUrl": "https://sqs/main"}]
    sqs.get_queue_attributes.return_value = {"Attributes": {"QueueArn": "arn:aws:sqs:eu-west-1:0:dlq"}}
    ddb = MagicMock()
    logs = MagicMock()

    client_map = {
        "s3": s3,
        "s3vectors": s3v,
        "kms": kms,
        "secretsmanager": sm,
        "sqs": sqs,
        "dynamodb": ddb,
        "logs": logs,
    }
    factory = MagicMock(spec=AWSClientFactory)
    factory.region_name = "eu-west-1"
    factory.get_client.side_effect = lambda name: client_map[name]

    bootstrap_aws_resources(factory=factory, s3_bucket="eu-bucket", queue_prefix="q")
    s3.create_bucket.assert_called_once_with(
        Bucket="eu-bucket",
        CreateBucketConfiguration={"LocationConstraint": "eu-west-1"},
    )
    lc_rules = s3.put_bucket_lifecycle_configuration.call_args.kwargs["LifecycleConfiguration"]["Rules"]
    rule_ids = [r["ID"] for r in lc_rules]
    assert "existing-archive-rule" in rule_ids
    assert "expire-abandoned-staging-uploads" in rule_ids
    staging_rule = next(r for r in lc_rules if r["ID"] == "expire-abandoned-staging-uploads")
    assert staging_rule["Expiration"]["Days"] == 15

    # If lifecycle read fails with AccessDenied, bootstrap MUST NOT overwrite existing lifecycle rules,
    # emits an operator warning, and if CreateQueue hits QueueAlreadyExists it reconciles via set_queue_attributes.
    s3.put_bucket_lifecycle_configuration.reset_mock()
    s3.get_bucket_lifecycle_configuration.side_effect = _client_error("AccessDenied")
    sqs.create_queue.side_effect = [{"QueueUrl": "https://sqs/dlq"}, _client_error("QueueAlreadyExists")]
    sqs.get_queue_url.return_value = {"QueueUrl": "https://sqs/main"}
    with caplog.at_level("WARNING", logger="scripts.bootstrap_aws_emulator"):
        bootstrap_aws_resources(factory=factory, s3_bucket="eu-bucket", queue_prefix="q")
    s3.put_bucket_lifecycle_configuration.assert_not_called()
    sqs.set_queue_attributes.assert_called_once()
    assert any("skipping staging expiration rule update" in rec.message for rec in caplog.records)
