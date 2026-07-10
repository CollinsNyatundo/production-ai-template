import logging
import re
from typing import List

from app.models import SearchDocument

logger = logging.getLogger("app.security.content_filter")

# Shared secret/PII patterns, reused by output_filter.py for the symmetric check
# on LLM-generated text. These are regex heuristics, not a substitute for a real
# PII/DLP engine (e.g. Microsoft Presidio, AWS Comprehend) - false negatives on
# formats not listed here are expected. They catch the common, high-confidence
# cases: contact PII and provider API key formats.
SECRET_PATTERNS = {
    "openai_key": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "nvidia_key": re.compile(r"nvapi-[A-Za-z0-9_-]{20,}"),
    "langsmith_key": re.compile(r"ls(v2_(pt|sk)|__)[A-Za-z0-9_]{15,}"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "generic_bearer": re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]{20,}=*"),
}

PII_PATTERNS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone": re.compile(r"\b\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
}


def redact(text: str, include_pii: bool = True) -> str:
    """Redacts known secret formats (always) and PII formats (optionally) from text."""
    for label, pattern in SECRET_PATTERNS.items():
        text = pattern.sub(f"[REDACTED_{label.upper()}]", text)
    if include_pii:
        for label, pattern in PII_PATTERNS.items():
            text = pattern.sub(f"[REDACTED_{label.upper()}]", text)
    return text


class ContentFilter:
    async def filter_contexts(self, contexts: List[SearchDocument]) -> List[SearchDocument]:
        """Redacts secrets/PII from retrieved document content before it reaches the LLM."""
        logger.info(f"Filtering {len(contexts)} retrieved document(s) for PII and leaked secrets...")
        for doc in contexts:
            cleaned = redact(doc.content, include_pii=True)
            if cleaned != doc.content:
                logger.warning(f"Redacted sensitive content from document '{doc.metadata.get('source', 'unknown')}'")
            doc.content = cleaned
        return contexts


content_filter = ContentFilter()
