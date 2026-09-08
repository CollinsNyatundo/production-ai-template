import socket

import pytest
from fastapi import Request

from app.config import Settings
from app.main import app, query_endpoint
from app.models import QueryRequest, QueryResponse
from app.security.auth import User
from app.services.connectors.file_extractor import extract_file_content
from app.services.connectors.web_scraper import SimpleTextExtractor, _validate_public_http_url
from app.services.ingestion_service import (
    ACTIVE_COLLECTIONS,
    INGESTION_JOBS,
    create_ingestion_job,
    delete_collection,
    get_job_status,
    list_collections,
)
from app.services.rag_pipeline import rag_pipeline


def test_ingestion_records_are_tenant_scoped():
    INGESTION_JOBS.clear()
    job_id = create_ingestion_job("web", "https://example.com", "tenant-a", "example")
    assert get_job_status(job_id, "tenant-a") is not None
    assert get_job_status(job_id, "tenant-b") is None


def test_collection_listing_and_deletion_are_tenant_scoped():
    ACTIVE_COLLECTIONS["scope-test"] = {"id": "scope-test", "tenant_id": "tenant-a"}
    assert all(item.get("tenant_id") == "tenant-a" for item in list_collections("tenant-a"))
    assert delete_collection("scope-test", "tenant-b") is False
    assert delete_collection("scope-test", "tenant-a") is True


def test_file_extractor_rejects_unsupported_and_invalid_uploads():
    assert extract_file_content("notes.txt", b"hello") == "hello"
    assert extract_file_content("data.json", b'{"ok": true}') == '{\n  "ok": true\n}'
    with pytest.raises(ValueError, match="Unsupported"):
        extract_file_content("payload.exe", b"binary")
    with pytest.raises(ValueError, match="Invalid JSON"):
        extract_file_content("payload.json", b"not-json")


@pytest.mark.asyncio
async def test_url_validator_rejects_private_destinations(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))],
    )
    with pytest.raises(ValueError, match="Private"):
        await _validate_public_http_url("http://example.test/private")


@pytest.mark.asyncio
async def test_url_validator_accepts_public_http_destination(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    assert await _validate_public_http_url("https://example.test/page") == "https://example.test/page"


def test_html_extractor_omits_script_content():
    parser = SimpleTextExtractor()
    parser.feed("<head><title>Hidden</title></head><h1>Visible</h1><script>secret()</script><p>Body</p>")
    extracted = parser.get_text()
    assert "Visible" in extracted and "Body" in extracted
    assert "Hidden" not in extracted and "secret" not in extracted


def test_jwt_algorithm_uses_correct_environment_name(monkeypatch):
    monkeypatch.setenv("JWT_ALGORITHM", "HS512")
    configured = Settings(_env_file=None)
    assert configured.jwt_algorithm == "HS512"


@pytest.mark.asyncio
async def test_query_scope_is_derived_from_authenticated_user(monkeypatch):
    async def fake_execute(payload):
        assert payload.tenant_id == "tenant-a"
        assert payload.user_id == "alice"
        assert payload.actor_permission == "high"
        assert payload.session_id == "tenant-a:session-1"
        return QueryResponse(answer="ok")

    monkeypatch.setattr(rag_pipeline, "execute", fake_execute)
    payload = QueryRequest(
        query="hello",
        session_id="session-1",
        tenant_id="attacker-tenant",
        user_id="attacker-user",
        actor_permission="low",
    )
    user = User(username="alice", tenant_id="tenant-a", permission_level="high")
    request = Request({"type": "http", "method": "POST", "path": "/api/query", "headers": []})
    response = await query_endpoint(payload, request, user)
    assert response.answer == "ok"


def test_streaming_endpoint_is_registered():
    assert any(getattr(route, "path", None) == "/api/query/stream" for route in app.routes)
