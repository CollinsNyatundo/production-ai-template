"""
Tests that mock only the LLM boundary (app.services.llm_client.llm_client.chat),
per .claude/rules/testing.md's "mock external calls" guidance - everything else
(tool registry, executor control flow, circuit breaker) runs for real. This is
the pattern the original codebase's testing rule called for but never actually
followed, since the "mock" used to be permanently hardcoded into the runtime
modules themselves rather than swapped in only at test time.

Each test injects its own isolated AsyncCircuitBreaker rather than using the
shared app-wide llm_breaker singleton, so these tests can't interfere with
each other (or with tests/test_harness.py's real, unmocked calls) regardless
of execution order.
"""

import asyncio
import json
from types import SimpleNamespace
from typing import Dict
from unittest.mock import AsyncMock

import pytest
from openai.types.chat import ChatCompletionMessageFunctionToolCall
from openai.types.chat.chat_completion_message_function_tool_call import Function

from app.agents.executor import agent_executor
from app.security.resilience import AsyncCircuitBreaker


def _fake_tool_call(call_id: str, name: str, arguments: Dict[str, object]) -> ChatCompletionMessageFunctionToolCall:
    # A real SDK object, not a loose SimpleNamespace - executor.py narrows
    # tool_calls with isinstance(call, ChatCompletionMessageFunctionToolCall)
    # (the SDK's tool_calls type is a union that also includes a "custom tool"
    # variant we don't support), so a duck-typed fake would fail that check
    # and silently exercise the wrong code path instead of what these tests
    # are meant to verify.
    return ChatCompletionMessageFunctionToolCall(
        id=call_id, type="function", function=Function(name=name, arguments=json.dumps(arguments))
    )


def _fake_response(content=None, tool_calls=None, prompt_tokens=10, completion_tokens=5):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


@pytest.mark.asyncio
async def test_agent_executor_real_tool_calling_loop(monkeypatch):
    """Verifies the executor: (1) calls the tool the mocked LLM asks for, (2) feeds
    the observation back into the next turn, (3) terminates on the mocked LLM's
    plain-text final answer, (4) accumulates real token usage across both turns."""
    turn_1 = _fake_response(tool_calls=[_fake_tool_call("call_1", "vector_search", {"query": "hybrid retrieval"})])
    turn_2 = _fake_response(content="Hybrid retrieval combines dense and sparse search.")
    mock_chat = AsyncMock(side_effect=[turn_1, turn_2])

    monkeypatch.setattr("app.agents.executor.llm_client.chat", mock_chat)
    monkeypatch.setattr("app.agents.executor.llm_breaker", AsyncCircuitBreaker("IsolatedTestBreaker"))

    result = await agent_executor.execute_trajectory(
        "mocked-tool-loop-session", "How does hybrid retrieval work?", actor_permission="low"
    )

    assert result["completed"] is True
    assert result["final_answer"] == "Hybrid retrieval combines dense and sparse search."
    assert len(result["trajectory"]) == 2
    assert result["trajectory"][0]["tool"] == "vector_search"
    assert result["trajectory"][1]["tool"] is None
    assert result["token_usage"] == {"prompt_tokens": 20, "completion_tokens": 10}
    assert mock_chat.call_count == 2


@pytest.mark.asyncio
async def test_agent_executor_forces_answer_on_final_turn(monkeypatch):
    """If the mocked LLM keeps requesting tools past max_turns, the executor must
    force tool_choice='none' on the last turn so it always terminates with an
    actual answer instead of looping forever or ending on a bare tool call."""
    always_wants_tool = _fake_response(tool_calls=[_fake_tool_call("call_x", "vector_search", {"query": "x"})])
    final_forced_answer = _fake_response(content="Best answer I can give with what I have.")

    mock_chat = AsyncMock(side_effect=[always_wants_tool, always_wants_tool, always_wants_tool, always_wants_tool, final_forced_answer])
    monkeypatch.setattr("app.agents.executor.llm_client.chat", mock_chat)
    monkeypatch.setattr("app.agents.executor.llm_breaker", AsyncCircuitBreaker("IsolatedTestBreaker2"))

    result = await agent_executor.execute_trajectory("forced-final-turn-session", "test query", actor_permission="low")

    assert result["completed"] is True
    assert result["final_answer"] == "Best answer I can give with what I have."
    # Last call must have been made with tools disabled (tool_choice="none")
    last_call_kwargs = mock_chat.call_args_list[-1].kwargs
    assert last_call_kwargs.get("tool_choice") == "none"
    assert last_call_kwargs.get("tools") is None


@pytest.mark.asyncio
async def test_agent_executor_degrades_gracefully_on_repeated_llm_failure(monkeypatch):
    """Reproduces, deterministically, the exact gap that real testing against the
    (network-blocked) NVIDIA/LangSmith endpoints caught during development: the
    original except clauses only handled CircuitBreakerOpenException and
    LLMNotConfiguredError, not the underlying error the breaker sees before it
    trips open. This asserts the executor returns a safe fallback instead of
    raising, both before and after the breaker actually trips."""
    test_breaker = AsyncCircuitBreaker("IsolatedFailureBreaker", failure_threshold=2, recovery_timeout=60)
    monkeypatch.setattr("app.agents.executor.llm_breaker", test_breaker)
    monkeypatch.setattr("app.agents.executor.llm_client.chat", AsyncMock(side_effect=RuntimeError("simulated upstream 500")))

    result = await agent_executor.execute_trajectory("failing-llm-session", "test query", actor_permission="low")

    assert result["completed"] is True
    assert "temporarily unable" in result["final_answer"].lower()
    assert test_breaker.failure_count == 1  # first failure recorded, not yet tripped

    # A second failing session should trip the breaker open, and still degrade safely.
    result_2 = await agent_executor.execute_trajectory("failing-llm-session-2", "another query", actor_permission="low")
    assert result_2["completed"] is True
    assert test_breaker.state == "OPEN"


def test_settings_reject_default_secret_outside_development(monkeypatch):
    """Regression guard for the fail-open auth default: unauthenticated requests
    get full admin access when app_env == 'development' (app/security/auth.py),
    so any non-development environment MUST reject the published default secret."""
    from app.config import Settings

    # conftest.py sets a real JWT_SECRET for the rest of the suite; clear it here
    # so this test exercises the actual class default, not the ambient one.
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)

    with pytest.raises(ValueError, match="Refusing to start"):
        Settings(_env_file=None, APP_ENV="production")

    # A real secret in a non-development env is fine.
    s = Settings(_env_file=None, APP_ENV="production", JWT_SECRET="a-real-generated-secret")
    assert s.app_env == "production"

    # Development is exempt (local convenience), and test/testing tolerate it too.
    for env in ("development", "test", "testing"):
        Settings(_env_file=None, APP_ENV=env)


def test_cors_default_is_not_wildcard():
    """Regression guard: allow_origins=['*'] combined with allow_credentials=True
    (as configured in app/main.py) lets any site make credentialed cross-origin
    requests. The default origin list must be an explicit, narrow allow-list."""
    from app.config import Settings

    origins = Settings(_env_file=None).cors_allowed_origins
    assert "*" not in origins
    assert all(o.startswith("http") for o in origins)


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_serializes_concurrent_probes():
    """Regression guard for the HALF-OPEN concurrency fix: a burst of concurrent
    callers arriving right as the breaker becomes eligible for recovery must
    result in exactly ONE actual downstream call, with the rest fast-failing -
    not all of them rushing the recovering service at once."""
    breaker = AsyncCircuitBreaker("ConcurrencyTestBreaker", failure_threshold=1, recovery_timeout=0.1)

    async def failing_call():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await breaker.call(failing_call)
    assert breaker.state == "OPEN"
    await asyncio.sleep(0.15)  # let recovery_timeout elapse

    call_count = 0

    async def slow_recovering_call():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.1)
        return "ok"

    results = await asyncio.gather(
        *[breaker.call(slow_recovering_call) for _ in range(5)], return_exceptions=True
    )
    successes = [r for r in results if r == "ok"]

    assert call_count == 1, f"expected exactly 1 downstream call, got {call_count}"
    assert len(successes) == 1
    assert breaker.state == "CLOSED"


def test_session_id_scoped_by_tenant():
    """Regression guard: two different tenants using the same client-facing
    session_id string must not collide in storage. Previously the raw
    client-supplied session_id was used directly as the storage key with no
    ownership check - any authenticated caller could read or clear any
    session_id they knew or guessed."""
    from app.main import _scoped_session_id
    from app.security.auth import User

    user_a = User(username="alice", role="user", permission_level="low", scopes=["read"], tenant_id="tenant-a")
    user_b = User(username="bob", role="user", permission_level="low", scopes=["read"], tenant_id="tenant-b")

    scoped_a = _scoped_session_id(user_a, "shared-session-name")
    scoped_b = _scoped_session_id(user_b, "shared-session-name")

    assert scoped_a != scoped_b
    assert "tenant-a" in scoped_a
    assert "tenant-b" in scoped_b
