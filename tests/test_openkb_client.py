from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.components.openkb_client import OpenKBClient
from app.security.resilience import AsyncCircuitBreaker, CircuitBreakerOpenException


@pytest.mark.asyncio
async def test_openkb_client_ingest_success():
    breaker = AsyncCircuitBreaker('TestIngestBreaker')
    client = OpenKBClient(base_url='http://mock-openkb:7566', breaker=breaker)
    mock_resp = {'status': 'success', 'doc_id': 'doc_123'}

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_resp
    mock_response.raise_for_status.return_value = None

    with patch.object(httpx.AsyncClient, 'post', return_value=mock_response):
        res = await client.ingest('https://example.com/doc.pdf')
        assert res == mock_resp


@pytest.mark.asyncio
async def test_openkb_client_query_success():
    breaker = AsyncCircuitBreaker('TestQueryBreaker')
    client = OpenKBClient(base_url='http://mock-openkb:7566', breaker=breaker)
    mock_results = [{'content': 'Test result', 'relevance': 0.95}]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'results': mock_results}
    mock_response.raise_for_status.return_value = None

    with patch.object(httpx.AsyncClient, 'post', return_value=mock_response):
        res = await client.query('what is test?')
        assert res == mock_results


@pytest.mark.asyncio
async def test_openkb_client_circuit_breaker_fast_fail():
    breaker = AsyncCircuitBreaker('TestOpenKBBreaker', failure_threshold=1, recovery_timeout=60)
    client = OpenKBClient(base_url='http://invalid-host:7566', breaker=breaker)

    with patch.object(httpx.AsyncClient, 'post', side_effect=httpx.ConnectError('Connection refused')):
        with pytest.raises(httpx.ConnectError):
            await client.query('test')

        with pytest.raises(CircuitBreakerOpenException):
            await client.query('test')
