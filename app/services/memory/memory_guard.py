import re
from typing import List, Pattern, Tuple


class MemoryGuard:
    """Adversarial Security Guard that filters prompt injections, secrets, and system instructions from memory."""

    DANGEROUS_PATTERNS: List[Pattern[str]] = [
        re.compile(r"ignore\s+(all\s+)?(previous\s+)?instructions", re.IGNORECASE),
        re.compile(r"system\s+prompt", re.IGNORECASE),
        re.compile(r"grant\s+admin", re.IGNORECASE),
        re.compile(r"bypass\s+security", re.IGNORECASE),
        re.compile(r"api[-_]?key\s*[:=]\s*\w+", re.IGNORECASE),
        re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
        re.compile(r"Bearer\s+[a-zA-Z0-9\._\-]+", re.IGNORECASE),
    ]

    def validate_memory_candidate(self, text: str) -> Tuple[bool, str]:
        """Validates candidate memory text for security vulnerabilities. Returns (is_safe, reason)."""
        clean_text = text.strip()
        if not clean_text or len(clean_text) < 4:
            return False, "Memory candidate is too short or empty."

        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.search(clean_text):
                return False, f"Memory candidate matched suspicious security pattern '{pattern.pattern}'."

        return True, "Memory candidate verified safe."

    def sanitize_for_prompt_injection(self, memories: List[str]) -> List[str]:
        """Sanitizes memory strings before injecting into the system prompt."""
        safe_memories = []
        for mem in memories:
            is_safe, _ = self.validate_memory_candidate(mem)
            if is_safe:
                # Strip special formatting characters that could trigger markdown/XML injections
                sanitized = mem.replace("<", "&lt;").replace(">", "&gt;")
                safe_memories.append(sanitized)

        return safe_memories


memory_guard = MemoryGuard()
