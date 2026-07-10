import json
import logging
import re
from typing import List

from app.security.resilience import llm_breaker
from app.services.llm_client import llm_client

logger = logging.getLogger("app.agents.query_decomposer")

_DECOMPOSE_PROMPT = """Does the following query contain multiple distinct questions that
would each need separate research to answer well? If yes, split it into a JSON array of
standalone sub-questions. If no, return a JSON array containing only the original query
unchanged.

Query: {query}

Respond with ONLY a JSON array of strings, no other text.
"""


class QueryDecomposer:
    async def decompose(self, query: str) -> List[str]:
        logger.info(f"Decomposing query: '{query}'")
        try:
            return await llm_breaker.call(self._execute_decompose, query)
        except Exception as e:
            logger.warning(f"LLM unavailable for decomposition ({e}); treating query as a single question.")
            return [query]

    async def _execute_decompose(self, query: str) -> List[str]:
        response = await llm_client.chat(
            messages=[{"role": "user", "content": _DECOMPOSE_PROMPT.format(query=query)}],
            temperature=0.0,
            max_tokens=300,
        )
        content = response.choices[0].message.content or "[]"
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if not match:
            raise ValueError(f"Could not find a JSON array in decomposer output: {content!r}")
        sub_queries = json.loads(match.group(0))
        if not isinstance(sub_queries, list) or not all(isinstance(q, str) for q in sub_queries):
            raise ValueError(f"Decomposer output was not a list of strings: {sub_queries!r}")
        return sub_queries or [query]


query_decomposer = QueryDecomposer()
