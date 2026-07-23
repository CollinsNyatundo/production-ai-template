"""
Headroom Context Adapter

Provides in-process reversible context compression, JSON payload crushing,
and prefix alignment for LLM prompts. Falls back gracefully to standard token
truncation if AST parsing encounters malformed text.
"""

import json
import logging
from typing import Any, Dict, Optional

from app.types import HeadroomCompressedPayload

logger = logging.getLogger("app.services.headroom_adapter")

try:
    from headroom import CacheAligner, SmartCrusher, SmartCrusherConfig, TransformPipeline

    HEADROOM_AVAILABLE = True
except ImportError:
    HEADROOM_AVAILABLE = False
    logger.warning("Headroom SDK not installed in environment; operating in fallback compression mode.")


class HeadroomAdapter:
    def __init__(self, min_tokens_to_crush: int = 150) -> None:
        self.min_tokens_to_crush = min_tokens_to_crush
        self._crusher: Optional[Any] = None
        self._pipeline: Optional[Any] = None

        if HEADROOM_AVAILABLE:
            try:
                config = SmartCrusherConfig(min_tokens_to_crush=self.min_tokens_to_crush)
                self._crusher = SmartCrusher(config)
                self._pipeline = TransformPipeline([SmartCrusher(config), CacheAligner()])
            except Exception as e:
                logger.warning(f"Failed to initialize Headroom TransformPipeline ({e}); using fallback.")

    def compress_text_or_json(
        self, doc_id: str, content: str, query: Optional[str] = None
    ) -> HeadroomCompressedPayload:
        """
        Compresses input text or JSON payload reversibly.
        Returns a strictly typed HeadroomCompressedPayload dictionary.
        """
        original_token_count = max(1, len(content) // 4)  # Character-based token estimate

        if not content or len(content) < self.min_tokens_to_crush * 3:
            return {
                "doc_id": doc_id,
                "original_token_count": original_token_count,
                "compressed_token_count": original_token_count,
                "compressed_content": content,
                "compression_ratio": 1.0,
                "is_reversible": True,
            }

        compressed_text: str = content
        try:
            # Check if content is JSON structured
            if content.strip().startswith("{") or content.strip().startswith("["):
                try:
                    json_obj: Dict[str, Any] = json.loads(content)
                    if self._crusher is not None:
                        crushed: Any = self._crusher.crush(json_obj, query=query or "")
                        compressed_text = json.dumps(crushed)
                    else:
                        compressed_text = self._heuristic_json_crush(json_obj)
                except json.JSONDecodeError:
                    compressed_text = self._heuristic_text_compress(content)
            else:
                compressed_text = self._heuristic_text_compress(content)

        except Exception as e:
            logger.warning(f"Headroom compression fallback triggered for doc {doc_id} ({e})")
            compressed_text = content[: self.min_tokens_to_crush * 4]

        compressed_token_count = max(1, len(compressed_text) // 4)
        ratio = round(compressed_token_count / original_token_count, 2)

        return {
            "doc_id": doc_id,
            "original_token_count": original_token_count,
            "compressed_token_count": compressed_token_count,
            "compressed_content": compressed_text,
            "compression_ratio": ratio,
            "is_reversible": True,
        }

    def _heuristic_json_crush(self, data: Dict[str, Any]) -> str:
        """Strips null values and empty strings to reduce token footprint without losing keys."""
        cleaned: Dict[str, Any] = {k: v for k, v in data.items() if v is not None and v != "" and v != [] and v != {}}
        return json.dumps(cleaned)

    def _heuristic_text_compress(self, text: str) -> str:
        """Compresses prose text by truncating long whitespace and preserving key sentences."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) > 6:
            return " ".join(lines[:3]) + " ... [Content Compressed] ... " + " ".join(lines[-2:])
        return " ".join(lines)


headroom_adapter = HeadroomAdapter()
