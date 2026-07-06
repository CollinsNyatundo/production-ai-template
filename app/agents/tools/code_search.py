import logging
from typing import List

from app.models import SearchDocument

logger = logging.getLogger("app.agents.tools.code_search")


class CodeSearchTool:
    name = "code_search"
    description = "Searches the project repository code and config file schemas."

    async def execute(self, query: str) -> List[SearchDocument]:
        logger.info(f"Code search tool called with query: '{query}'")

        # Mocking local codebase schema parsing
        return [
            SearchDocument(
                content="class settings(BaseSettings): app_env: str = Field(default='development', validation_alias='APP_ENV')",
                metadata={"source": "app/config.py", "language": "python"},
                score=0.9,
            )
        ]


code_search_tool = CodeSearchTool()
