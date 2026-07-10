import logging
import re
from typing import Tuple

logger = logging.getLogger("app.security.input_guard")

# Deterministic first-pass filter for obvious prompt-injection phrasing. This is
# a heuristic, not a robust defense - rephrasing, unicode tricks, or translation
# will bypass regex matching. It exists to catch the cheap/obvious cases before
# they reach the LLM at near-zero cost and latency; a production system should
# layer a real classifier (Llama Guard, NeMo Guardrails) behind this, not
# instead of it. \s+ tolerates extra whitespace between words that plain
# substring matching would miss.
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts?)", re.IGNORECASE),
    re.compile(r"(reveal|show|print|repeat)\s+(the\s+)?system\s+prompt", re.IGNORECASE),
    re.compile(r"overwrite\s+(your\s+)?instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+you\s+(are|have)|an?)\s+.*\bwithout\s+(restrictions|limits|filters)", re.IGNORECASE),
]


class InputGuard:
    async def validate(self, query: str) -> Tuple[bool, str]:
        logger.info(f"Scanning query for safety: '{query}'")

        for pattern in _INJECTION_PATTERNS:
            if pattern.search(query):
                return False, f"Potential prompt injection detected (pattern: '{pattern.pattern}')"

        return True, "Safe"


input_guard = InputGuard()
