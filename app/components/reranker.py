import logging
from typing import List
from app.models import SearchDocument

logger = logging.getLogger("app.components.reranker")

class Reranker:
    def __init__(self):
        # In production, load a cross-encoder model (e.g. Cohere Rerank or HuggingFace cross-encoder)
        logger.info("Initializing Cross-Encoder Reranker component...")

    async def rerank(self, query: str, documents: List[SearchDocument]) -> List[SearchDocument]:
        logger.info(f"Reranking {len(documents)} documents for query: '{query}'")
        
        # Simple simulated reranking: sort by original retrieval score
        # In production, cross-encoders compute exact query-passage semantic match scores.
        sorted_docs = sorted(documents, key=lambda d: d.score, reverse=True)
        return sorted_docs

reranker = Reranker()
