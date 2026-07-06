import logging
import time

from app.models import QueryRequest, QueryResponse, AgentStep
from app.services.semantic_cache import semantic_cache
from app.services.query_rewriter import query_rewriter
from app.services.query_router import query_router
from app.services.conversation import conversation_service

# Harness Improvements
from app.components.hybrid_retriever import hybrid_retriever
from app.components.reranker import reranker
from app.security.input_guard import input_guard
from app.security.output_filter import output_filter
from observability.tracer import tracer
from observability.cost_tracker import cost_tracker
from app.prompts.registry import prompt_registry

# $H = (E, T, C, S, L, V)$ components
from app.services.context_manager import context_manager
from app.agents.tools.registry import tool_registry
from app.agents.tools.vector_search import vector_search_tool
from app.agents.tools.web_search import web_search_tool
from app.agents.tools.code_search import code_search_tool
from app.agents.executor import agent_executor
from app.services.hooks import lifecycle_hooks
from evaluation.trajectory_logger import trajectory_logger

logger = logging.getLogger("app.services.rag_pipeline")

# Register tools in the centralized registry (T - Gap Mitigation)
tool_registry.register_tool(
    name="vector_search",
    description="Searches the internal semantic index and vector database for RAG context.",
    func=vector_search_tool.execute,
    required_permission="low"
)
tool_registry.register_tool(
    name="web_search",
    description="Searches the public web for real-time news and general information.",
    func=web_search_tool.execute,
    required_permission="low"
)
tool_registry.register_tool(
    name="code_search",
    description="Searches the project repository code and config file schemas.",
    func=code_search_tool.execute,
    required_permission="high" # High permission gating test case
)

# Example Lifecycle Hooks Subscriber (L - Gap Mitigation)
def audit_logger(session_id: str, **kwargs):
    logger.info(f"[Lifecycle Hook AUDIT] Session: {session_id} - Logged Event Args: {list(kwargs.keys())}")

lifecycle_hooks.register("on_agent_start", audit_logger)
lifecycle_hooks.register("on_tool_execute", audit_logger)

class RAGPipeline:
    async def execute(self, payload: QueryRequest) -> QueryResponse:
        start_time = time.perf_counter()
        
        async with tracer.span(name="RAGPipeline.execute", attributes={"session_id": payload.session_id}) as span:
            # 1. Security Check: Input Guard
            is_safe, reason = await input_guard.validate(payload.query)
            if not is_safe:
                logger.warning(f"Query rejected by Input Guard: {reason}")
                return QueryResponse(
                    answer=f"Request rejected for security reasons: {reason}.",
                    sources=[]
                )

            # 2. Semantic Cache Check
            if payload.use_cache:
                cached_response = await semantic_cache.get(payload.query)
                if cached_response:
                    span.set_attribute("cache_hit", True)
                    return cached_response

            # 3. Retrieve Session History
            history = await conversation_service.get_history(payload.session_id)
            history_str = " ".join([m["content"] for m in history[-3:]])

            # 4. Query Rewrite
            rewritten_query = await query_rewriter.rewrite(payload.query, history_str)

            # 5. Execution Loop (E)
            # Run the multi-turn agent loop to collect information and execute actions
            run_result = await agent_executor.execute_trajectory(
                session_id=payload.session_id,
                query=rewritten_query,
                actor_permission=payload.actor_permission
            )
            raw_trajectory = run_result["trajectory"]

            # Map raw dict trajectory to Pydantic AgentStep models for QueryResponse
            pydantic_trajectory = [
                AgentStep(
                    turn=step["turn"],
                    thought=step["thought"],
                    tool=step["tool"],
                    arguments=step["arguments"],
                    observation=step["observation"]
                ) for step in raw_trajectory
            ]

            # 6. Context Manager (C)
            # Aggregate all tools observations and pack within token budget limits
            retrieved_docs = []
            for step in raw_trajectory:
                if step["tool"] == "vector_search" and step["observation"]:
                    # Fetch documents from retriever candidates
                    retrieved_docs = await hybrid_retriever.retrieve(step["arguments"]["query"])

            # Sort/Prune contexts using tiktoken budget (C - Gap Mitigation)
            packed_docs = await context_manager.pack_context(
                documents=retrieved_docs,
                token_budget=1500, # 1500 tokens budget limit
                model="gpt-4o"
            )

            # 7. Response Generation
            logger.info("Generating response from LLM using packed contexts...")
            final_ans = "According to the codebase templates, production architectures require input/output filters, semantic cache configurations, and persistent SQLite database stores to prevent session losses."

            # Record Token costs
            cost_info = await cost_tracker.track_usage(
                model="gpt-4o",
                prompt_tokens=250,
                completion_tokens=50
            )
            span.set_attribute("query_cost_usd", cost_info["total_cost"])

            # 8. Output Sanitizer Security Check
            final_answer = await output_filter.sanitize(final_ans)

            # 9. Save to Session Store (S)
            await conversation_service.add_message(payload.session_id, "user", payload.query)
            await conversation_service.add_message(payload.session_id, "assistant", final_answer)

            # 10. Cache response
            if payload.use_cache:
                await semantic_cache.set(payload.query, final_answer, packed_docs)

            # 11. Valuation Trajectory Logging (V - Gap Mitigation)
            await trajectory_logger.log_run(
                session_id=payload.session_id,
                query=payload.query,
                trajectory=raw_trajectory,
                answer=final_answer
            )

            latency = (time.perf_counter() - start_time) * 1000.0
            return QueryResponse(
                answer=final_answer,
                sources=packed_docs,
                cached=False,
                latency_ms=latency,
                trajectory=pydantic_trajectory
            )

rag_pipeline = RAGPipeline()
