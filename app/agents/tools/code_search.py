import logging
import re
from pathlib import Path
from typing import List

from app.models import SearchDocument

logger = logging.getLogger("app.agents.tools.code_search")

# Repo root, derived from this file's location (app/agents/tools/code_search.py ->
# parents[3] is the repo root) rather than a user-controlled or configurable path,
# so there's no path-traversal surface here.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SEARCHABLE_EXTENSIONS = {".py", ".yml", ".yaml", ".toml", ".json"}
_EXCLUDED_DIR_NAMES = {".git", "__pycache__", "node_modules", ".venv", "venv", ".pytest_cache", "assets"}
_MAX_RESULTS = 5
_CONTEXT_LINES = 2


class CodeSearchTool:
    name = "code_search"
    description = "Searches the project repository code and config file schemas."

    async def execute(self, query: str) -> List[SearchDocument]:
        logger.info(f"Code search tool called with query: '{query}'")
        if not query.strip():
            return []

        pattern = re.compile(re.escape(query), re.IGNORECASE)
        results: List[SearchDocument] = []

        for path in self._iter_searchable_files():
            if len(results) >= _MAX_RESULTS:
                break
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue

            for i, line in enumerate(lines):
                if pattern.search(line):
                    start, end = max(0, i - _CONTEXT_LINES), min(len(lines), i + _CONTEXT_LINES + 1)
                    snippet = "\n".join(lines[start:end])
                    rel_path = path.relative_to(_REPO_ROOT).as_posix()
                    results.append(
                        SearchDocument(
                            content=snippet,
                            metadata={"source": rel_path, "language": path.suffix.lstrip("."), "line": i + 1},
                            score=0.9,
                        )
                    )
                    break  # one match per file keeps results diverse rather than one noisy file

            if len(results) >= _MAX_RESULTS:
                break

        if not results:
            return [
                SearchDocument(
                    content=f"No matches for '{query}' in repository source files.",
                    metadata={"source": "code_search", "language": "none"},
                    score=0.0,
                )
            ]
        return results

    def _iter_searchable_files(self):
        for path in _REPO_ROOT.rglob("*"):
            if not path.is_file() or path.suffix not in _SEARCHABLE_EXTENSIONS:
                continue
            if any(part in _EXCLUDED_DIR_NAMES for part in path.parts):
                continue
            yield path


code_search_tool = CodeSearchTool()
