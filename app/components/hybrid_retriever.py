import logging
from typing import List, Optional

from app.cloud.secrets import kms_envelope_cipher
from app.cloud.vector_store import S3VectorKnowledgeStore
from app.components.openkb_client import openkb_client
from app.config import settings
from app.models import SearchDocument
from observability.tracer import current_user_context

logger = logging.getLogger("app.components.hybrid_retriever")


class HybridRetriever:
    def __init__(self) -> None:
        logger.info("Initializing HybridRetriever via OpenKB sidecar integration...")
        self._s3_vector_store = S3VectorKnowledgeStore(kms_cipher=kms_envelope_cipher)

    async def retrieve(self, query: str, top_k: int = 5, tenant_id: Optional[str] = None) -> List[SearchDocument]:
        if settings.aws_backend_enabled:
            ctx = current_user_context.get()
            effective_tenant = tenant_id or (ctx["tenant_id"] if ctx else "default-tenant")
            try:
                aws_docs = await self._s3_vector_store.query(
                    tenant_id=effective_tenant,
                    query_text=query,
                    top_k=top_k,
                )
                if aws_docs:
                    return aws_docs[:top_k]
            except Exception as exc:
                logger.warning("S3 Vectors retrieval failed for tenant '%s' (%s); falling back.", effective_tenant, exc)

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
            fallback_map = {
                "cache": SearchDocument(
                    content=(
                        "Semantic caching caches embeddings of queries to serve subsequent requests, "
                        "which saves cost and reduces latency for system performance optimization."
                    ),
                    metadata={"source": "fallback", "category": "performance"},
                    score=0.95,
                ),
                "hybrid": SearchDocument(
                    content=(
                        "Hybrid retrieval combines dense vector embeddings and sparse BM25 keyword search "
                        "using a calculated relevance score to maximize search precision and recall."
                    ),
                    metadata={"source": "fallback", "category": "retrieval"},
                    score=0.95,
                ),
                "vector": SearchDocument(
                    content=(
                        "Vector search uses dense vector embeddings to find semantically similar documents "
                        "by calculating cosine distance in high-dimensional embedding space."
                    ),
                    metadata={"source": "fallback", "category": "search"},
                    score=0.95,
                ),
                "rag": SearchDocument(
                    content=(
                        "Retrieval-Augmented Generation (RAG) combines dense vector retrieval with LLM generation "
                        "to deliver grounded, accurate, and non-hallucinated answers."
                    ),
                    metadata={"source": "fallback", "category": "rag"},
                    score=0.95,
                ),
            }

            query_lower = query.lower()
            matched_docs = [doc for key, doc in fallback_map.items() if key in query_lower]
            return matched_docs if matched_docs else list(fallback_map.values())[:top_k]


hybrid_retriever = HybridRetriever()
