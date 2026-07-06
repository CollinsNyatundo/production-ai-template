import logging
from contextlib import asynccontextmanager
from typing import Dict, Any

logger = logging.getLogger("app.observability.tracer")

class MockSpan:
    def __init__(self, name: str, attributes: Dict[str, Any] = None):
        self.name = name
        self.attributes = attributes or {}

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value
        logger.info(f"Span '{self.name}' Attribute Set: {key}={value}")

class Tracer:
    def __init__(self):
        logger.info("Initializing OpenTelemetry Tracer Adapter...")

    @asynccontextmanager
    async def span(self, name: str, attributes: Dict[str, Any] = None):
        # MOCK OTEL SPAN: In production, hooks into:
        # from opentelemetry import trace
        # tracer = trace.get_tracer(__name__)
        # with tracer.start_as_current_span(name) as span: ...
        
        logger.info(f"==> Trace Span START: '{name}'")
        span_obj = MockSpan(name, attributes)
        
        try:
            yield span_obj
        finally:
            logger.info(f"<== Trace Span END: '{name}'")

tracer = Tracer()
