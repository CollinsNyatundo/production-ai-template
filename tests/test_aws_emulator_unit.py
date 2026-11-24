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
async def test_semantic_cache_generation_blocks_stale_writes_and_auth_keeps_401() -> None:
    from fastapi import HTTPException

    from app.security.auth import create_access_token, get_current_user
    from app.services.semantic_cache import SemanticCache

    cache = SemanticCache()
    gen_before = cache.get_tenant_generation("tenant-a")
    await cache.invalidate_tenant("tenant-a")
    # Stale in-flight write captured before invalidation must be skipped
    await cache.set("tenant-a", "handbook policy", "stale answer", [], expected_generation=gen_before)
    assert await cache.get("tenant-a", "handbook policy") is None

    # Signed token with unknown subject must return 401 (never 503)
    unknown_token = create_access_token({"sub": "nonexistent-user"})
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token=unknown_token, api_key=None)
    assert exc_info.value.status_code == 401


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


def test_bootstrap_passes_location_constraint_outside_us_east_1() -> None:
    s3 = MagicMock()
    s3.head_bucket.side_effect = _client_error("404")
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
