import logging
from typing import List, Optional

import tiktoken

from app.models import SearchDocument
from app.services.headroom_adapter import headroom_adapter

logger = logging.getLogger("app.services.context_manager")


class ContextManager:
    # NOTE ON ACCURACY: tiktoken only ships real tokenizers for OpenAI models.
    # The model actually wired up for generation is an NVIDIA-hosted Llama
    # model (see app.config.settings.nvidia_model), which uses a different
    # tokenizer entirely. Counting against "gpt-4o" here is a deliberate,
    # reasonably-conservative proxy for budgeting purposes, not an exact count
    # for whatever model is actually configured - there is no tiktoken-based
    # way to get that exactly for a non-OpenAI model.
    def __init__(self, default_model: str = "gpt-4o", default_budget: int = 2000):
        self.default_model = default_model
        self.default_budget = default_budget
        logger.info(f"Context Manager initialized. Model: {default_model}, Budget: {default_budget} tokens")

    def _get_encoding(self, model: str):
        try:
            return tiktoken.encoding_for_model(model)
        except Exception as e:
            logger.debug(f"No direct tiktoken mapping for model '{model}' ({e}); trying cl100k_base fallback.")
            try:
                return tiktoken.get_encoding("cl100k_base")
            except Exception as e2:
                # Both lookups failed - most likely no network access to fetch
                # the BPE file and no pre-warmed cache (see app/Dockerfile for
                # the build-time fix). Signal the caller to use the character
                # estimate instead of crashing a budgeting utility.
                logger.warning(f"tiktoken encodings unavailable ({e2}); falling back to character-based estimate.")
                return None

    def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        model = model or self.default_model
        enc = self._get_encoding(model)
        if enc is None:
            return self._estimate_tokens_by_chars(text)
        return len(enc.encode(text))

    @staticmethod
    def _estimate_tokens_by_chars(text: str) -> int:
        """Rough English-text heuristic (~4 chars/token) used only if tiktoken's
        encoding files can't be loaded at all (no cache, no network)."""
        return max(1, len(text) // 4)

    async def pack_context(
        self,
        documents: List[SearchDocument],
        token_budget: Optional[int] = None,
        model: Optional[str] = None,
    ) -> List[SearchDocument]:
        token_budget = token_budget or self.default_budget
        model = model or self.default_model

        logger.info(f"Packing context documents into budget: {token_budget} tokens (Model: {model})")

        # Sort documents by relevance score descending first
        sorted_docs = sorted(documents, key=lambda d: d.score, reverse=True)
        packed_docs = []
        current_tokens = 0

        for idx, doc in enumerate(sorted_docs):
            doc_id = str(doc.metadata.get("id") or doc.metadata.get("source") or f"doc_{idx}")
            compressed_res = headroom_adapter.compress_text_or_json(doc_id, doc.content)

            # If Headroom compressed the document, update content and log ratio
            if compressed_res["compression_ratio"] < 1.0:
                doc.content = f"{compressed_res['compressed_content']}\n[DocID: {doc_id} | Compressed {compressed_res['compression_ratio']}x]"
                doc.metadata["headroom_compressed"] = True
                doc.metadata["headroom_doc_id"] = doc_id

            doc_tokens = self.count_tokens(doc.content, model)

            # If adding this doc fits within the budget, take it entirely
            if current_tokens + doc_tokens <= token_budget:
                packed_docs.append(doc)
                current_tokens += doc_tokens
                logger.info(
                    f"Document {doc.metadata.get('source')} added. Tokens: {doc_tokens}. Total: {current_tokens}"
                )
            else:
                # PITFALL MITIGATION: Instead of crashing or ignoring context window overflow,
                # we dynamically truncate the document to pack the remaining token budget.
                remaining_tokens = token_budget - current_tokens
                if remaining_tokens > 20:  # Only truncate if it is worth adding a snippet
                    truncated_content = self._truncate_text_to_tokens(doc.content, remaining_tokens, model)
                    doc.content = truncated_content + "\n[Content truncated due to token budget limits]"
                    doc.score = doc.score * 0.8  # Lower score due to truncation
                    packed_docs.append(doc)
                    current_tokens += remaining_tokens
                    logger.info(
                        f"Document {doc.metadata.get('source')} truncated to fit remaining {remaining_tokens} tokens."
                    )
                break  # Reached budget threshold

        return packed_docs

    def _truncate_text_to_tokens(self, text: str, target_tokens: int, model: str) -> str:
        enc = self._get_encoding(model)
        if enc is None:
            return text[: target_tokens * 4]
        tokens = enc.encode(text)
        truncated_tokens = tokens[:target_tokens]
        return str(enc.decode(truncated_tokens))


context_manager = ContextManager()
