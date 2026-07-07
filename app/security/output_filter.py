import logging

logger = logging.getLogger("app.security.output_filter")


class OutputFilter:
    async def sanitize(self, response: str) -> str:
        logger.info("Scanning LLM response output for hallucinations and safety compliance...")

        # MOCK OUTPUT FILTER: In production, check alignment, factual correctness,
        # toxic outputs, or accidental API key leaks.

        sanitized = response.strip()

        # Example leak prevention simulation:
        if "sk-" in sanitized:
            logger.warning("Potential OpenAI API key leaked in response! Redacting...")
            # Simple regex replacement mock
            sanitized = "[REDACTED KEY]"

        return sanitized


output_filter = OutputFilter()
