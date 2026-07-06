import logging
from typing import List
from app.models import SearchDocument

logger = logging.getLogger("app.agents.tools.web_search")

class WebSearchTool:
    name = "web_search"
    description = "Searches the public web for real-time news and general information."

    async def execute(self, query: str) -> List[SearchDocument]:
        logger.info(f"Web search tool called with query: '{query}'")
        
        # Mocking external web search (e.g. Brave Search / Google Search API connection)
        # Prevents local data indexing dependency for general knowledge queries
        return [
            SearchDocument(
                content=f"According to online sources, '{query}' is currently discussed in public blogs as a modern RAG practice.",
                metadata={"source": "https://brave.com/search", "category": "web"},
                score=0.8
            )
        ]

web_search_tool = WebSearchTool()
