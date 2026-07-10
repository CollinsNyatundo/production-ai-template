import logging

from app.prompts.registry import prompt_registry
from app.security.resilience import llm_breaker
from app.services.llm_client import llm_client

logger = logging.getLogger("app.services.query_rewriter")


class QueryRewriter:
    async def _execute_rewrite(self, query: str, history: str) -> str:
        if not history:
            return query.strip()

        prompt_template = await prompt_registry.get_prompt("query_rewrite_prompt")
        prompt = prompt_template.format(history=history, query=query)

        response = await llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=150,
        )
        rewritten = (response.choices[0].message.content or "").strip()
        return rewritten or query.strip()

    async def rewrite(self, query: str, history: str = "") -> str:
        logger.info(f"Rewriting query: '{query}'")
        try:
            return await llm_breaker.call(self._execute_rewrite, query, history)
        except Exception as e:
            logger.warning(f"LLM unavailable for query rewrite ({e}); falling back to original query.")
            return query


query_rewriter = QueryRewriter()
