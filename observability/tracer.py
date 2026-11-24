import logging
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import AsyncIterator, Dict, Optional

from app.config import settings
from app.types import OTelAttributeValue, UserContext

logger = logging.getLogger("app.observability.tracer")

# ContextVar to store tenant and user metadata for automatic trace propagation (S - Pattern)
current_user_context: ContextVar[Optional[UserContext]] = ContextVar("current_user_context", default=None)


class MockSpan:
    def __init__(self, name: str, attributes: Optional[Dict[str, OTelAttributeValue]] = None):
        self.name = name
        self.attributes: Dict[str, OTelAttributeValue] = attributes or {}
        # Automatically enrich spans with current contextvar metadata if present
        ctx = current_user_context.get()
        if ctx:
            self.attributes.update(
                {
                    "tenant.id": ctx["tenant_id"],
                    "user.id": ctx["username"],
                    "user.role": ctx["role"],
                    "app.env": ctx.get("app_env", "production"),
                }
            )

    def set_attribute(self, key: str, value: OTelAttributeValue) -> None:
        self.attributes[key] = value
        logger.info(f"Span '{self.name}' Attribute Set: {key}={value}")


class Tracer:
    def __init__(self):
        logger.info("Initializing OpenTelemetry Tracer Adapter...")

    @asynccontextmanager
    async def span(
        self, name: str, attributes: Optional[Dict[str, OTelAttributeValue]] = None
    ) -> AsyncIterator[MockSpan]:
        logger.info(f"==> Trace Span START: '{name}'")
        start_perf = time.perf_counter()
        start_epoch = time.time()
        span_obj = MockSpan(name, attributes)

        # Merge initial attributes
        if attributes:
            for k, v in attributes.items():
                span_obj.set_attribute(k, v)

        try:
            yield span_obj
        finally:
            duration_ms = (time.perf_counter() - start_perf) * 1000.0
            end_epoch = time.time()
            # Output full span trace attributes log for mock visualization
            logger.info(f"<== Trace Span END: '{name}' | Attributes: {span_obj.attributes}")
            if settings.aws_backend_enabled:
                from app.cloud.telemetry import aws_observability_sink

                await aws_observability_sink.emit_span(
                    name=name,
                    duration_ms=duration_ms,
                    attributes=span_obj.attributes,
                    start_epoch=start_epoch,
                    end_epoch=end_epoch,
                )


tracer = Tracer()
