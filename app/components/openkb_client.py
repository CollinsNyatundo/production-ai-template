import json
import logging
import os
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from app.config import settings
from app.security.resilience import AsyncCircuitBreaker, CircuitBreakerOpenException, search_tool_breaker

logger = logging.getLogger("app.components.openkb_client")


class OpenKBClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        breaker: Optional[AsyncCircuitBreaker] = None,
    ):
        self.base_url = (base_url or settings.openkb_base_url).rstrip("/")
        self.timeout = timeout or settings.openkb_timeout_s
        self.breaker = breaker or search_tool_breaker

    async def _post_json(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        async def _request() -> Dict[str, Any]:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    url = f"{self.base_url}{endpoint}"
                    response = await client.post(url, json=payload)
                    response.raise_for_status()
                    res: Dict[str, Any] = response.json()
                    return res
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                logger.warning(f"OpenKB sidecar offline or unreachable ({e}); returning empty response for fallback.")
                return {}

        try:
            res_dict = await self.breaker.call(_request)
            return res_dict if isinstance(res_dict, dict) else {}
        except (httpx.HTTPError, CircuitBreakerOpenException) as e:
            logger.warning(f"OpenKB request failed ({e}); proceeding with fallback.")
            return {}

    async def ingest(self, url_or_path: str) -> Dict[str, Any]:
        logger.info(f"Ingesting into OpenKB: {url_or_path}")
        payload = {"url": url_or_path} if url_or_path.startswith("http") else {"file_path": url_or_path}
        return await self._post_json("/api/v1/documents", payload)

    async def query(self, query_str: str, limit: int = 5) -> List[Dict[str, Any]]:
        logger.info(f"Querying OpenKB: {query_str}")
        if os.getenv("SKIP_OPENKB") == "true" or os.getenv("CI") == "true":
            logger.info("Skipping OpenKB in CI environment, using fallback.")
            return []
        payload = {"query": query_str, "limit": limit}
        res = await self._post_json("/api/v1/query", payload)
        if isinstance(res, dict) and "results" in res:
            results: List[Dict[str, Any]] = res["results"]
            return results
        elif isinstance(res, list):
            return res
        return []

    async def query_stream(self, prompt: str, session_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        url = f"{self.base_url}/api/v1/chat/completions"
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
        if session_id:
            payload["session_id"] = session_id

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data_json = json.loads(data_str)
                            delta = data_json.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if delta:
                                yield delta
                        except json.JSONDecodeError:
                            yield data_str


openkb_client = OpenKBClient()
