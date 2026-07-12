import logging

from app.security.content_filter import redact

logger = logging.getLogger("app.security.output_filter")


class OutputFilter:
    async def sanitize(self, response: str) -> str:
        """
        Redacts leaked secret formats from LLM-generated output. PII is
        intentionally NOT redacted here (include_pii=False) - the answer may
        legitimately need to reference PII the user themselves provided
        earlier in the conversation; content_filter.py already stripped PII
        out of retrieved *source* documents before they ever reached the model.
        """
        logger.info("Scanning LLM response output for leaked secrets...")
        sanitized = redact(response.strip(), include_pii=False)
        if sanitized != response.strip():
            logger.warning("Potential secret leaked in LLM response - redacted before returning to caller.")
        return sanitized


output_filter = OutputFilter()
