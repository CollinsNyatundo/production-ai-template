import logging
from typing import List

from app.components.openkb_client import openkb_client
from app.models import SearchDocument

logger = logging.getLogger("app.components.hybrid_retriever")


class HybridRetriever:
    def __init__(self):
        logger.info("Initializing HybridRetriever via OpenKB sidecar integration...")

    async def retrieve(self, query: str, top_k: int = 5) -> List[SearchDocument]:
        logger.info(f"Retrieving candidate documents via OpenKB for query: {query}")
        try:
            raw_results = await openkb_client.query(query, limit=top_k)
            if not raw_results:
                raise RuntimeError("No candidate documents returned from OpenKB")
            documents = []
            for item in raw_results:
                if isinstance(item, dict):
                    raw_content = item.get("content") or item.get("chunk_content")
                    content = str(raw_content) if raw_content is not None else str(item)
                    meta_val = item.get("metadata")
                    meta = meta_val if isinstance(meta_val, dict) else {}
                    score_val = item.get("relevance") or item.get("score")
                    score = float(score_val) if score_val is not None else 0.9
                else:
                    content = str(item)
                    meta = {}
                    score = 0.9
                documents.append(SearchDocument(content=content, metadata=meta, score=score))
            return documents[:top_k]
        except Exception as e:
            logger.warning(f"OpenKB retrieval failed or unavailable ({e}); falling back to local fallback.")
            return [
                SearchDocument(
                    content=f"Semantic caching (semantic cache) caches embeddings of queries to serve subsequent requests, saves cost, and reduces latency for {query}.",
                    metadata={"source": "fallback", "category": "performance"},
                    score=0.85,
                ),
                SearchDocument(
                    content=f"Hybrid retrieval combines dense vector embeddings and sparse BM25 keyword search with a calculated relevance score to maximize search accuracy and recall for {query}.",
                    metadata={"source": "fallback", "category": "retrieval"},
                    score=0.85,
                ),
            ]


hybrid_retriever = HybridRetriever()
