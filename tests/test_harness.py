import os
import time

import jwt
import pytest
from fastapi import HTTPException

from app.agents.executor import agent_executor
from app.agents.tools.registry import tool_registry
from app.models import QueryRequest, SearchDocument
from app.security.auth import (
    ALGORITHM,
    SECRET_KEY,
    create_access_token,
    get_current_user,
)
from app.security.resilience import AsyncCircuitBreaker, CircuitBreakerOpenException
from app.services.context_manager import context_manager
from app.services.conversation import conversation_service
from app.services.hooks import lifecycle_hooks
from app.services.rag_pipeline import rag_pipeline
from app.services.state_store import state_store


@pytest.mark.asyncio
async def test_context_manager_tokens():
    # Test token counting
    tokens = context_manager.count_tokens("Semantic caching is awesome.", model="gpt-4o")
    assert tokens > 0

    # Test packing and truncation
    docs = [
        SearchDocument(
            content="Large context content " * 100,
            score=0.9,
            metadata={"source": "doc1"},
        ),
        SearchDocument(content="Short content", score=0.95, metadata={"source": "doc2"}),
    ]
    packed = await context_manager.pack_context(docs, token_budget=50, model="gpt-4o")
    # Assert that the budget was respected and the large doc was truncated
    assert len(packed) == 2
    assert "truncated" in packed[1].content.lower()


@pytest.mark.asyncio
async def test_tool_registry_permissions():
    # Assert schemas auto-generation
    schemas = tool_registry.get_tool_schemas()
    assert len(schemas) > 0
    assert any(s["name"] == "code_search" for s in schemas)

    # Test permission gating (T - Gap Mitigation)
    # Executing code_search (high permission) with low permission actor should get blocked
    res_blocked = await tool_registry.execute_tool("code_search", {"query": "config"}, actor_permission="low")
    assert "blocked" in res_blocked.lower()

    # Executing with high permission actor should succeed and return a real match
    # from the actual repository source tree (code_search.py now genuinely greps
    # app/ rather than returning one hardcoded snippet).
    res_success = await tool_registry.execute_tool("code_search", {"query": "config"}, actor_permission="high")
    assert len(res_success) > 0
    assert "config" in res_success[0].content.lower()
    assert res_success[0].metadata["source"]  # a real relative file path, not a hardcoded placeholder


@pytest.mark.asyncio
async def test_lifecycle_hooks():
    events_logged = []

    def test_subscriber(session_id: str, **kwargs):
        events_logged.append(session_id)

    lifecycle_hooks.register("on_agent_start", test_subscriber)
    await lifecycle_hooks.emit("on_agent_start", session_id="test-session-123")

    assert "test-session-123" in events_logged


@pytest.mark.asyncio
async def test_sqlalchemy_state_store():
    session_id = "sqlalchemy-test-session"

    # Clear any previous run
    await state_store.clear_history(session_id)

    # Save messages
    await state_store.save_message(session_id, "user", "Hello SQLAlchemy")
    await state_store.save_message(session_id, "assistant", "Hello human")

    # Retrieve messages
    history = await state_store.get_history(session_id)
    assert len(history) == 2
    assert history[0]["content"] == "Hello SQLAlchemy"

    # Checkpoint snapshot testing (S - Gap Mitigation)
    state = {"stage": "reasoning"}
    trajectory = [{"turn": 1, "thought": "running"}]
    await state_store.save_checkpoint(session_id, current_step=1, state=state, trajectory=trajectory)

    checkpoint = await state_store.load_checkpoint(session_id)
    assert checkpoint is not None
    assert checkpoint["current_step"] == 1
    assert checkpoint["state"]["stage"] == "reasoning"


@pytest.mark.asyncio
async def test_agent_executor_loop():
    # Execute full trajectory
    res = await agent_executor.execute_trajectory("exec-session", "What is caching?", actor_permission="low")
    assert "trajectory" in res
    assert len(res["trajectory"]) > 0
    assert res["completed"] is True


@pytest.mark.asyncio
async def test_full_harness_pipeline():
    # Test full end-to-end run
    payload = QueryRequest(query="caching", session_id="pipeline-session", use_cache=False)
    response = await rag_pipeline.execute(payload)

    assert response.answer is not None
    assert len(response.trajectory) > 0
    assert response.latency_ms > 0

    # Verify trajectory JSONL log was written (V - Gap Mitigation)
    assert os.path.exists("evaluation/eval_results/trajectory_runs.jsonl")


@pytest.mark.asyncio
async def test_jwt_auth():
    # 1. Generate access token
    token = create_access_token({"sub": "admin"})
    assert token is not None

    # Decode verification
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "admin"

    # 2. Get user dependency resolver
    user = await get_current_user(token=token)
    assert user.username == "admin"
    assert user.permission_level == "high"
    assert user.tenant_id == "tenant-alpha"

    # Invalid Token check
    with pytest.raises(HTTPException) as excinfo:
        await get_current_user(token="invalid.bearer.token")
    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_circuit_breaker():
    breaker = AsyncCircuitBreaker("TestBreaker", failure_threshold=2, recovery_timeout=0.2)

    async def mock_failing_call():
        raise ValueError("Mock LLM Down")

    async def mock_successful_call():
        return "Success"

    # Call 1: failure
    with pytest.raises(ValueError):
        await breaker.call(mock_failing_call)
    assert breaker.state == "CLOSED"
    assert breaker.failure_count == 1

    # Call 2: failure -> trips to OPEN
    with pytest.raises(ValueError):
        await breaker.call(mock_failing_call)
    assert breaker.state == "OPEN"
    assert breaker.failure_count == 2

    # Call 3: blocked immediately
    with pytest.raises(CircuitBreakerOpenException):
        await breaker.call(mock_successful_call)

    # Wait for recovery timeout
    time.sleep(0.25)

    # Call 4: successful call recovers circuit
    result = await breaker.call(mock_successful_call)
    assert result == "Success"
    assert breaker.state == "CLOSED"
    assert breaker.failure_count == 0


@pytest.mark.asyncio
async def test_conversation_clear_history_actually_clears():
    """Regression guard for the frontend's Clear Conversation button, which
    previously called nothing at all and just displayed a fake success
    message. Verifies the service it now genuinely calls (via
    DELETE /api/session/{id} in app/main.py) actually empties history."""
    session_id = "clear-history-test-session"
    await conversation_service.add_message(session_id, "user", "hello")
    await conversation_service.add_message(session_id, "assistant", "hi there")

    history_before = await conversation_service.get_history(session_id)
    assert len(history_before) == 2

    await conversation_service.clear_history(session_id)

    history_after = await conversation_service.get_history(session_id)
    assert history_after == []
