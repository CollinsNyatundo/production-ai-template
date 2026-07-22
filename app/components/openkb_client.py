import json
import logging
from typing import AsyncGenerator, Dict, List, Optional

import httpx

from app.config import settings
from app.security.resilience import AsyncCircuitBreaker, search_tool_breaker

logger = logging.getLogger('app.components.openkb_client')


class OpenKBClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        breaker: Optional[AsyncCircuitBreaker] = None,
    ):
        self.base_url = (base_url or settings.openkb_base_url).rstrip('/')
        self.timeout = timeout or settings.openkb_timeout_s
        self.breaker = breaker or search_tool_breaker

    async def _post_json(self, endpoint: str, payload: dict) -> dict:
        async def _request() -> dict:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                url = f'{self.base_url}{endpoint}'
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return response.json()

        return await self.breaker.call(_request)

    async def ingest(self, url_or_path: str) -> dict:
        logger.info(f'Ingesting into OpenKB: {url_or_path}')
        payload = {'url': url_or_path} if url_or_path.startswith('http') else {'file_path': url_or_path}
        return await self._post_json('/api/v1/documents', payload)

    async def query(self, query_str: str, limit: int = 5) -> List[Dict]:
        logger.info(f'Querying OpenKB: {query_str}')
        payload = {'query': query_str, 'limit': limit}
        res = await self._post_json('/api/v1/query', payload)
        if isinstance(res, dict) and 'results' in res:
            return res['results']
        elif isinstance(res, list):
            return res
        return [{'content': str(res), 'relevance': 1.0}]

    async def query_stream(self, prompt: str, session_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        url = f'{self.base_url}/api/v1/chat/completions'
        payload = {
            'messages': [{'role': 'user', 'content': prompt}],
            'stream': True,
        }
        if session_id:
            payload['session_id'] = session_id

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream('POST', url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        data_str = line[6:].strip()
                        if data_str == '[DONE]':
                            break
                        try:
                            data_json = json.loads(data_str)
                            delta = data_json.get('choices', [{}])[0].get('delta', {}).get('content', '')
                            if delta:
                                yield delta
                        except json.JSONDecodeError:
                            yield data_str


openkb_client = OpenKBClient()
