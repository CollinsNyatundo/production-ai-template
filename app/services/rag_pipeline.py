import logging
import time

from app.models import QueryRequest, QueryResponse
from app.services.semantic_cache import semantic_cache
from app.services.query_rewriter import query_rewriter
from app.services.query_router import query_router
from app.services.conversation import conversation_service

# Placeholder imports that will be created next
from app.components.hybrid_retriever import hybrid_retriever
from app.components.reranker import reranker
from app.security.input_guard import input_guard
from app.security.output_filter import output_filter
from app.observability.tracer import tracer
from app.observability.cost_tracker import cost_tracker
from app.prompts.registry import prompt_registry

logger = logging.getLogger("app.services.rag_pipeline")

class RAGPipeline:
    async def execute(self, payload: QueryRequest) -> QueryResponse:
        # Start Trace Span
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
            history_str = " ".join([m["content"] for m in history[-3:]]) # Take last 3 messages

            # 4. Query Rewrite
            rewritten_query = await query_rewriter.rewrite(payload.query, history_str)

            # 5. Query Routing
            target_route = await query_router.route(rewritten_query)
            span.set_attribute("target_route", target_route)

            # 6. Document Retrieval
            # (In production, the router directs to either vector_search, web_search, etc.)
            raw_docs = await hybrid_retriever.retrieve(rewritten_query)

            # 7. Document Reranking
            ranked_docs = await reranker.rerank(rewritten_query, raw_docs)

            # 8. Fetch Prompt Template
            system_prompt = await prompt_registry.get_prompt("rag_system_prompt")
            user_prompt = f"Context:\n" + "\n".join([d.content for d in ranked_docs]) + f"\n\nQuestion: {rewritten_query}"

            # 9. LLM Generation
            logger.info("Generating response from LLM...")
            # Simulate LLM Response. In production, connect to OpenAI/Anthropic SDK
            # and count tokens using tiktoken.
            simulated_response = f"This is a simulated production RAG answer answering '{payload.query}' based on context about hybrid search and observability."
            
            # Record Token costs
            cost_info = await cost_tracker.track_usage(
                model="gpt-4o",
                prompt_tokens=250,
                completion_tokens=50
            )
            span.set_attribute("query_cost_usd", cost_info["total_cost"])

            # 10. Security Check: Output Filter
            final_answer = await output_filter.sanitize(simulated_response)

            # 11. Save to session memory
            await conversation_service.add_message(payload.session_id, "user", payload.query)
            await conversation_service.add_message(payload.session_id, "assistant", final_answer)

            # 12. Cache response
            if payload.use_cache:
                await semantic_cache.set(payload.query, final_answer, ranked_docs)

            return QueryResponse(
                answer=final_answer,
                sources=ranked_docs,
                cached=False
            )

rag_pipeline = RAGPipeline()
