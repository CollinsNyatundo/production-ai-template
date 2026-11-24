"""Offline unit tests for app.cloud adapters (no live AWS Emulator required)."""

from __future__ import annotations

import base64
import json
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from app.cloud.client import AWSClientFactory
from app.cloud.queue_store import DynamoDBStateRepository, SQSIngestionQueue
from app.cloud.secrets import AWSSecretsProvider, KMSEnvelopeCipher
from app.cloud.telemetry import AWSObservabilitySink
from app.cloud.vector_store import S3VectorKnowledgeStore, deterministic_embed, sanitize_index_name


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


def test_client_factory_caches_and_resets(monkeypatch: pytest.MonkeyPatch) -> None:
    created: List[str] = []

    def fake_boto3_client(service_name: str, **kwargs: Any) -> MagicMock:
        created.append(service_name)
        return MagicMock(name=f"client-{service_name}", kwargs=kwargs)

    monkeypatch.setattr("app.cloud.client.boto3.client", fake_boto3_client)
    factory = AWSClientFactory(region_name="us-east-1", endpoint_url="https://127.0.0.1:9297", ca_bundle="/tmp/ca.pem")
    c1 = factory.get_client("s3")
    c2 = factory.get_client("s3")
    assert c1 is c2
    assert created == ["s3"]

    factory.reset()
    factory.get_client("s3")
    assert created == ["s3", "s3"]


@pytest.mark.asyncio
async def test_secrets_provider_caches_and_parses_json() -> None:
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


@pytest.mark.asyncio
async def test_kms_cipher_enforces_context_and_rejects_client_error() -> None:
    kms = MagicMock()
    kms.encrypt.return_value = {"CiphertextBlob": b"cipher-bytes"}
    kms.decrypt.side_effect = [
        {"Plaintext": b"secret-doc"},
        _client_error("InvalidCiphertextException"),
    ]
    factory = MagicMock(spec=AWSClientFactory)
    factory.get_client.return_value = kms

    cipher = KMSEnvelopeCipher(factory=factory, key_id="key-123")
    enc = await cipher.encrypt_text("tenant-a", "secret-doc")
    assert base64.b64decode(enc) == b"cipher-bytes"
    assert await cipher.decrypt_text("tenant-a", enc) == "secret-doc"

    with pytest.raises(PermissionError, match="InvalidCiphertextException"):
        await cipher.decrypt_text("tenant-b", enc)


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
async def test_observability_sink_emits_and_handles_errors() -> None:
    clients: Dict[str, MagicMock] = {
        "cloudwatch": MagicMock(),
        "logs": MagicMock(),
        "xray": MagicMock(),
    }
    factory = MagicMock(spec=AWSClientFactory)
    factory.get_client.side_effect = lambda name: clients[name]

    sink = AWSObservabilitySink(factory=factory, namespace="NS", log_group="/test/lg")
    trace_id = await sink.emit_span("RAGPipeline.execute", 12.5, {"tenant.id": "tenant-a"})
    assert trace_id is not None and trace_id.startswith("1-")
    clients["cloudwatch"].put_metric_data.assert_called_once()
    clients["logs"].put_log_events.assert_called_once()
    clients["xray"].put_trace_segments.assert_called_once()

    clients["cloudwatch"].put_metric_data.side_effect = RuntimeError("network down")
    assert await sink.emit_span("RAGPipeline.execute", 1.0, {}) is None
