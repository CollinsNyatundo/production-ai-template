import logging
from typing import List

from app.models import SearchDocument

logger = logging.getLogger("app.agents.document_grader")


class DocumentGrader:
    def __init__(self):
        logger.info("Initializing Agentic Document Grader...")

    async def grade_documents(self, query: str, documents: List[SearchDocument]) -> List[SearchDocument]:
        logger.info(f"Grading {len(documents)} retrieved documents for query relevance...")

        # Fast, deterministic pre-filter: keyword overlap or a high retrieval
        # score. Intentionally not an LLM call (this runs on every tool result
        # in the live agent loop - see app/agents/executor.py - so keeping it
        # free/instant matters more than marginal precision gains would).
        relevant_docs = []
        for doc in documents:
            query_terms = set(query.lower().split())
            doc_content_lower = doc.content.lower()

            is_relevant = any(term in doc_content_lower for term in query_terms) or doc.score >= 0.8

            if is_relevant:
                logger.info(f"Document {doc.metadata.get('source')} graded RELEVANT.")
                relevant_docs.append(doc)
            else:
                logger.warning(f"Document {doc.metadata.get('source')} graded IRRELEVANT (Filtered out).")

        return relevant_docs


document_grader = DocumentGrader()
