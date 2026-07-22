import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.components.hybrid_retriever import hybrid_retriever
from app.components.reranker import reranker
from app.models import SearchDocument


@pytest.mark.asyncio
async def test_hybrid_retriever_mock():
    results = await hybrid_retriever.retrieve(query='caching', top_k=2)
    assert len(results) > 0
    assert any('cache' in doc.content.lower() for doc in results)


@pytest.mark.asyncio
async def test_reranker_reordering():
    docs = [
        SearchDocument(content='doc1', score=0.5),
        SearchDocument(content='doc2', score=0.9),
    ]

    with patch('app.components.reranker.llm_client.chat', new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value.choices = [
            type('Choice', (), {'message': type('Msg', (), {'content': '[0.5, 0.9]'})()})()
        ]
        sorted_docs = await reranker.rerank(query='test', documents=docs)
        assert sorted_docs[0].score == 0.9
        assert sorted_docs[1].score == 0.5
