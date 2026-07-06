import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any, Dict, Optional

logger = logging.getLogger("app.observability.tracer")

# ContextVar to store tenant and user metadata for automatic trace propagation (S - Pattern)
current_user_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "current_user_context", default=None
)


class MockSpan:
    def __init__(self, name: str, attributes: Dict[str, Any] = None):
        self.name = name
        self.attributes = attributes or {}
        # Automatically enrich spans with current contextvar metadata if present
        ctx = current_user_context.get()
        if ctx:
            self.attributes.update(
                {
                    "tenant.id": ctx.get("tenant_id"),
                    "user.id": ctx.get("username"),
                    "user.role": ctx.get("role"),
                    "app.env": ctx.get("app_env", "production"),
                }
            )

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value
        logger.info(f"Span '{self.name}' Attribute Set: {key}={value}")


class Tracer:
    def __init__(self):
        logger.info("Initializing OpenTelemetry Tracer Adapter...")

    @asynccontextmanager
    async def span(self, name: str, attributes: Dict[str, Any] = None):
        logger.info(f"==> Trace Span START: '{name}'")
        span_obj = MockSpan(name, attributes)

        # Merge initial attributes
        if attributes:
            for k, v in attributes.items():
                span_obj.set_attribute(k, v)

        try:
            yield span_obj
        finally:
            # Output full span trace attributes log for mock visualization
            logger.info(
                f"<== Trace Span END: '{name}' | Attributes: {span_obj.attributes}"
            )


tracer = Tracer()
