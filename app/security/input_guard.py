import logging
from typing import Tuple

logger = logging.getLogger("app.security.input_guard")

class InputGuard:
    async def validate(self, query: str) -> Tuple[bool, str]:
        logger.info(f"Scanning query for safety: '{query}'")
        
        # In production, this can call external services (e.g. Llama Guard, NeMo Guardrails)
        # or execute regexes to prevent prompt injection and PII leakage.
        
        query_lower = query.lower()
        
        # Injection detection simulation:
        injection_indicators = [
            "ignore previous instructions",
            "system prompt",
            "overwrite instructions",
            "you are now a"
        ]
        
        for indicator in injection_indicators:
            if indicator in query_lower:
                return False, f"Potential prompt injection detected (indicator: '{indicator}')"
                
        return True, "Safe"

input_guard = InputGuard()
