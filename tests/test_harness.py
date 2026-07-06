import pytest
import os
from app.models import QueryRequest, SearchDocument
from app.services.context_manager import context_manager
from app.agents.tools.registry import tool_registry
from app.services.hooks import lifecycle_hooks
from app.services.state_store import state_store
from app.agents.executor import agent_executor
from app.services.rag_pipeline import rag_pipeline

@pytest.mark.asyncio
async def test_context_manager_tokens():
    # Test token counting
    tokens = context_manager.count_tokens("Semantic caching is awesome.", model="gpt-4o")
    assert tokens > 0
    
    # Test packing and truncation
    docs = [
        SearchDocument(content="Large context content " * 100, score=0.9, metadata={"source": "doc1"}),
        SearchDocument(content="Short content", score=0.95, metadata={"source": "doc2"})
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

    # Executing with high permission actor should succeed
    res_success = await tool_registry.execute_tool("code_search", {"query": "config"}, actor_permission="high")
    assert "settings" in res_success[0].content.lower()

@pytest.mark.asyncio
async def test_lifecycle_hooks():
    events_logged = []
    
    def test_subscriber(session_id: str, **kwargs):
        events_logged.append(session_id)
        
    lifecycle_hooks.register("on_agent_start", test_subscriber)
    await lifecycle_hooks.emit("on_agent_start", session_id="test-session-123")
    
    assert "test-session-123" in events_logged

@pytest.mark.asyncio
async def test_sqlite_state_store():
    session_id = "sqlite-test-session"
    
    # Clear any previous run
    await state_store.clear_history(session_id)
    
    # Save messages
    await state_store.save_message(session_id, "user", "Hello SQLite")
    await state_store.save_message(session_id, "assistant", "Hello human")
    
    # Retrieve messages
    history = await state_store.get_history(session_id)
    assert len(history) == 2
    assert history[0]["content"] == "Hello SQLite"
    
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
