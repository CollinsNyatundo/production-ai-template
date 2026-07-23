"""
Unit tests for Headroom Context Adapter and Reversible Context Expansion Tool.
"""

import pytest

from app.agents.tools.registry import tool_registry
from app.models import SearchDocument
from app.services.context_manager import context_manager
from app.services.headroom_adapter import headroom_adapter


def test_headroom_adapter_short_text():
    content = "Short document content."
    res = headroom_adapter.compress_text_or_json("doc_1", content)
    assert res["doc_id"] == "doc_1"
    assert res["compressed_content"] == content
    assert res["compression_ratio"] == 1.0
    assert res["is_reversible"] is True


def test_headroom_adapter_json_crush():
    json_data = {
        "results": [
            {"id": 1, "name": "Item 1", "value": "A", "null_field": None, "empty": ""},
            {"id": 2, "name": "Item 2", "value": "B", "null_field": None, "empty": ""},
        ]
    }
    import json

    content = json.dumps(json_data) * 20  # Ensure > min_tokens_to_crush
    res = headroom_adapter.compress_text_or_json("doc_json", content)
    assert res["doc_id"] == "doc_json"
    assert isinstance(res["compressed_content"], str)
    assert res["is_reversible"] is True


def test_headroom_adapter_fallback():
    malformed = "Header Line 1\nHeader Line 2\nLine 3\nLine 4\nLine 5\nLine 6\nFooter 7\nFooter 8"
    res = headroom_adapter.compress_text_or_json("doc_fallback", malformed * 15)
    assert res["doc_id"] == "doc_fallback"
    assert "Compressed" in res["compressed_content"] or len(res["compressed_content"]) > 0


@pytest.mark.asyncio
async def test_context_manager_packing_with_headroom():
    docs = [
        SearchDocument(
            content="Heavy RAG document content with detailed domain explanations and long verbose paragraphs.\n" * 80,
            metadata={"source": "openkb_doc_1"},
            score=0.9,
        )
    ]
    packed = await context_manager.pack_context(docs, token_budget=1000)
    assert len(packed) == 1
    assert packed[0].metadata.get("headroom_compressed") is True


@pytest.mark.asyncio
async def test_expand_context_tool():
    schemas = tool_registry.get_tool_schemas()
    names = [s["name"] for s in schemas]
    assert "expand_context" in names

    result = await tool_registry.execute_tool("expand_context", {"document_id": "test_doc_123"})
    assert isinstance(result, str)
    assert "Uncompressed raw document content" in result
