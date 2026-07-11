import logging
import time

from langsmith import traceable

from app.agents.adaptive_router import adaptive_router
from app.agents.executor import agent_executor
from app.agents.query_decomposer import query_decomposer
from app.agents.tools.code_search import code_search_tool
from app.agents.tools.registry import tool_registry
from app.agents.tools.vector_search import vector_search_tool
from app.agents.tools.web_search import web_search_tool
from app.components.reranker import reranker
from app.config import settings
from app.models import AgentStep, QueryRequest, QueryResponse
from app.prompts.registry import prompt_registry
from app.security.input_guard import input_guard
from app.security.output_filter import output_filter
from app.security.resilience import llm_breaker
from app.services.context_manager import context_manager
from app.services.conversation import conversation_service
from app.services.hooks import lifecycle_hooks
from app.services.llm_client import llm_client
from app.services.query_rewriter import query_rewriter
from app.services.semantic_cache import semantic_cache
from evaluation.trajectory_logger import trajectory_logger
from observability.cost_tracker import cost_tracker
from observability.tracer import tracer

logger = logging.getLogger("app.services.rag_pipeline")

# Register tools in the centralized registry (T - Gap Mitigation)
tool_registry.register_tool(
    name="vector_search",
    description="Searches the internal semantic index and vector database for RAG context.",
    func=vector_search_tool.execute,
    required_permission="low",
)
tool_registry.register_tool(
    name="web_search",
    description="Searches the public web for real-time news and general information.",
    func=web_search_tool.execute,
    required_permission="low",
)
tool_registry.register_tool(
    name="code_search",
    description="Searches the project repository code and config file schemas.",
    func=code_search_tool.execute,
    required_permission="high",  # High permission gating test case
)


# Example Lifecycle Hooks Subscriber (L - Gap Mitigation)
def audit_logger(session_id: str, **kwargs):
    logger.info(f"[Lifecycle Hook AUDIT] Session: {session_id} - Logged Event Args: {list(kwargs.keys())}")


lifecycle_hooks.register("on_agent_start", audit_logger)
lifecycle_hooks.register("on_tool_execute", audit_logger)

_DIRECT_RESPONSE_MAX_TOKENS = 400


class RAGPipeline:
    @traceable(name="RAGPipeline.execute", run_type="chain")
    async def execute(self, payload: QueryRequest) -> QueryResponse:
        start_time = time.perf_counter()

        async with tracer.span(name="RAGPipeline.execute", attributes={"session_id": payload.session_id}) as span:
            # 1. Security Check: Input Guard
            is_safe, reason = await input_guard.validate(payload.query)
            if not is_safe:
                logger.warning(f"Query rejected by Input Guard: {reason}")
                return QueryResponse(
                    answer=f"Request rejected for security reasons: {reason}.",
                    sources=[],
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

            # 4. Query Rewrite (now a real LLM call; see app/services/query_rewriter.py)
            rewritten_query = await query_rewriter.rewrite(payload.query, history_str)

            # 5. Adaptive Routing - skip the full agent/tool loop (and, below,
            # decomposition) for short, low-complexity conversational input,
            # saving a full tool-calling round trip's worth of latency and tokens.
            route = await adaptive_router.route_adaptively(rewritten_query)
            span.set_attribute("route", route)

            if route == "direct_response":
                final_answer, raw_trajectory, token_usage = await self._direct_response(rewritten_query)
                packed_docs = []
            else:
                # 5b. Query Decomposition: for multi-part questions, surface the
                # sub-questions directly in what the agent sees rather than just
                # logging them - otherwise this is a real LLM call (latency + cost)
                # that changes nothing about the answer. Full parallel per-sub-query
                # retrieval is a bigger control-flow change than this covers; this
                # is the cheap middle ground - the single agent loop at least gets
                # an explicit checklist instead of silently trying to address a
                # compound question in one pass.
                sub_queries = await query_decomposer.decompose(rewritten_query)
                agent_query = rewritten_query
                if len(sub_queries) > 1:
                    span.set_attribute("decomposed_sub_queries", len(sub_queries))
                    logger.info(f"Query decomposed into {len(sub_queries)} sub-questions: {sub_queries}")
                    checklist = "\n".join(f"- {q}" for q in sub_queries)
                    agent_query = (
                        f"{rewritten_query}\n\nThis question has multiple parts - "
                        f"make sure your answer addresses each of these:\n{checklist}"
                    )

                run_result = await agent_executor.execute_trajectory(
                    session_id=payload.session_id,
                    query=agent_query,
                    actor_permission=payload.actor_permission,
                )
                raw_trajectory = run_result["trajectory"]
                final_answer = run_result["final_answer"]
                token_usage = run_result["token_usage"]

                # 6. Rerank (one LLM call across everything gathered in the whole
                # trajectory, not per tool call - see app/agents/executor.py for
                # why this doesn't live there) and apply a final context-budget
                # pass (each individual tool call was already budgeted to
                # PER_TOOL_CALL_TOKEN_BUDGET inside the executor; this caps the
                # combined total shown to the caller as "sources").
                reranked_docs = await reranker.rerank(rewritten_query, run_result["retrieved_documents"])
                packed_docs = await context_manager.pack_context(
                    documents=reranked_docs,
                    token_budget=1500,
                )

            pydantic_trajectory = [
                AgentStep(
                    turn=step["turn"],
                    thought=step["thought"],
                    tool=step["tool"],
                    arguments=step["arguments"],
                    observation=step["observation"],
                )
                for step in raw_trajectory
            ]

            # 7. Real token-usage-based cost tracking (was hardcoded constants before).
            cost_info = await cost_tracker.track_usage(
                model=settings.nvidia_model,
                prompt_tokens=token_usage["prompt_tokens"],
                completion_tokens=token_usage["completion_tokens"],
            )
            span.set_attribute("query_cost_usd", cost_info["total_cost"])

            # 8. Output Sanitizer Security Check
            final_answer = await output_filter.sanitize(final_answer)

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
                answer=final_answer,
            )

            latency = (time.perf_counter() - start_time) * 1000.0
            return QueryResponse(
                answer=final_answer,
                sources=packed_docs,
                cached=False,
                latency_ms=latency,
                trajectory=pydantic_trajectory,
            )

    async def _direct_response(self, query: str) -> "tuple[str, list, dict]":
        """Single LLM call, no tools, no retrieval - for adaptive_router's fast path."""
        system_prompt = await prompt_registry.get_prompt("rag_system_prompt")
        token_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        try:
            response = await llm_breaker.call(
                llm_client.chat,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ],
                max_tokens=_DIRECT_RESPONSE_MAX_TOKENS,
            )
            answer = response.choices[0].message.content or "I'm not sure how to respond to that."
            if response.usage:
                token_usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                }
        except Exception as e:
            logger.error(f"LLM unavailable for direct response: {e}")
            answer = "I'm temporarily unable to reach the language model. Please try again shortly."

        trajectory = [
            {"turn": 1, "thought": "Routed to direct response (short/simple query).", "tool": None, "arguments": {}, "observation": ""}
        ]
        return answer, trajectory, token_usage


rag_pipeline = RAGPipeline()
