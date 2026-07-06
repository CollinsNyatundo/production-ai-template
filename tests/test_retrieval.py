import pytest

from app.components.hybrid_retriever import hybrid_retriever
from app.components.reranker import reranker


@pytest.mark.asyncio
async def test_hybrid_retriever_mock():
    # Assert that retrieval yields documents
    results = await hybrid_retriever.retrieve(query="caching", top_k=2)
    assert len(results) > 0
    assert any("cache" in doc.content.lower() for doc in results)


@pytest.mark.asyncio
async def test_reranker_reordering():
    # Prepare mock inputs
    from app.models import SearchDocument

    docs = [
        SearchDocument(content="doc1", score=0.5),
        SearchDocument(content="doc2", score=0.9),
    ]

    # Assert reranking yields sorted documents by score
    sorted_docs = await reranker.rerank(query="test", documents=docs)
    assert sorted_docs[0].score == 0.9
    assert sorted_docs[1].score == 0.5
