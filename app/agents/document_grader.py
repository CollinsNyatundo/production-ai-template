import logging
from typing import List

from app.models import SearchDocument

logger = logging.getLogger("app.agents.document_grader")


class DocumentGrader:
    def __init__(self):
        logger.info("Initializing Agentic Document Grader...")

    async def grade_documents(
        self, query: str, documents: List[SearchDocument]
    ) -> List[SearchDocument]:
        logger.info(
            f"Grading {len(documents)} retrieved documents for query relevance..."
        )

        # MOCK AGENT LOOP: In production, this uses a small model (e.g. gpt-3.5)
        # to classify if a document snippet contains facts that address the query.
        # This prevents irrelevant documents from polluting LLM context windows.
        relevant_docs = []
        for doc in documents:
            # Simple keyword matching simulation to represent relevance decisions:
            # Let's say all mock docs containing words in the query are relevant.
            query_terms = set(query.lower().split())
            doc_content_lower = doc.content.lower()

            # Simulated grading logic:
            is_relevant = (
                any(term in doc_content_lower for term in query_terms)
                or doc.score >= 0.8
            )

            if is_relevant:
                logger.info(f"Document {doc.metadata.get('source')} graded RELEVANT.")
                relevant_docs.append(doc)
            else:
                logger.warning(
                    f"Document {doc.metadata.get('source')} graded IRRELEVANT (Filtered out)."
                )

        return relevant_docs


document_grader = DocumentGrader()
