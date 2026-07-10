import json
import logging
import re
from typing import List

from app.models import SearchDocument
from app.prompts.registry import prompt_registry
from app.security.resilience import llm_breaker
from app.services.llm_client import llm_client

logger = logging.getLogger("app.components.reranker")


class Reranker:
    def __init__(self):
        logger.info("Initializing LLM-based Reranker component...")

    async def rerank(self, query: str, documents: List[SearchDocument]) -> List[SearchDocument]:
        if len(documents) <= 1:
            return documents

        logger.info(f"Reranking {len(documents)} documents for query: '{query}'")
        try:
            scores = await llm_breaker.call(self._score_documents, query, documents)
            if len(scores) != len(documents):
                raise ValueError(f"Expected {len(documents)} scores, got {len(scores)}")
            for doc, score in zip(documents, scores):
                doc.score = float(score)
            return sorted(documents, key=lambda d: d.score, reverse=True)
        except Exception as e:
            logger.warning(f"LLM reranking unavailable ({e}); falling back to original retrieval score order.")
            return sorted(documents, key=lambda d: d.score, reverse=True)

    async def _score_documents(self, query: str, documents: List[SearchDocument]) -> List[float]:
        prompt_template = await prompt_registry.get_prompt("rerank_prompt")
        doc_list_str = "\n".join(f"{i + 1}. {d.content}" for i, d in enumerate(documents))
        prompt = prompt_template.format(query=query, documents=doc_list_str)

        response = await llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=200,
        )
        content = response.choices[0].message.content or "[]"

        # Models sometimes wrap JSON in a code fence despite instructions; strip it.
        match = re.search(r"\[[\d.,\s]*\]", content)
        if not match:
            raise ValueError(f"Could not find a JSON score array in reranker output: {content!r}")
        return json.loads(match.group(0))


reranker = Reranker()
