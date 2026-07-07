import logging
from typing import List

from app.components.hybrid_retriever import hybrid_retriever
from app.models import SearchDocument

logger = logging.getLogger("app.agents.tools.vector_search")


class VectorSearchTool:
    name = "vector_search"
    description = "Searches the internal semantic index and vector database for RAG context."

    async def execute(self, query: str) -> List[SearchDocument]:
        logger.info(f"Vector search tool called with query: '{query}'")
        return await hybrid_retriever.retrieve(query)


vector_search_tool = VectorSearchTool()
