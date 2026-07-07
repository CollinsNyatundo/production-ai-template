import logging
from typing import List, Optional

import tiktoken

from app.models import SearchDocument

logger = logging.getLogger("app.services.context_manager")


class ContextManager:
    def __init__(self, default_model: str = "gpt-4o", default_budget: int = 2000):
        self.default_model = default_model
        self.default_budget = default_budget
        logger.info(f"Context Manager initialized. Model: {default_model}, Budget: {default_budget} tokens")

    def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        model = model or self.default_model
        try:
            enc = tiktoken.encoding_for_model(model)
        except Exception:
            # Fallback encoding if model name isn't directly mapped in older tiktoken versions
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))

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

        for doc in sorted_docs:
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
        try:
            enc = tiktoken.encoding_for_model(model)
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")

        tokens = enc.encode(text)
        truncated_tokens = tokens[:target_tokens]
        return enc.decode(truncated_tokens)


context_manager = ContextManager()
