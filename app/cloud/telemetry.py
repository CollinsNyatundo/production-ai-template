"""AWS CloudWatch Metrics, CloudWatch Logs, and X-Ray observability sink."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from typing import Mapping, Optional

from botocore.exceptions import ClientError

from app.cloud.client import AWSClientFactory, aws_client_factory
from app.config import settings
from app.types import OTelAttributeValue

logger = logging.getLogger("app.cloud.telemetry")


class AWSObservabilitySink:
    """Emits spans, metrics, and structured logs to CloudWatch and AWS X-Ray."""

    def __init__(
        self,
        factory: AWSClientFactory = aws_client_factory,
        namespace: Optional[str] = None,
        log_group: Optional[str] = None,
        log_stream: str = "app-runtime",
    ) -> None:
        self._factory = factory
        self._namespace = namespace
        self._log_group = log_group
        self._log_stream = log_stream
        self._stream_initialized = False

    @property
    def namespace(self) -> str:
        return self._namespace or settings.aws_cloudwatch_namespace

    @property
    def log_group(self) -> str:
        return self._log_group or settings.aws_cloudwatch_log_group

    def _ensure_log_stream_sync(self) -> None:
        if self._stream_initialized:
            return
        logs = self._factory.get_client("logs")
        try:
            logs.create_log_group(logGroupName=self.log_group)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ResourceAlreadyExistsException":
                raise
        try:
            logs.create_log_stream(logGroupName=self.log_group, logStreamName=self._log_stream)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ResourceAlreadyExistsException":
                raise
        self._stream_initialized = True

    def _emit_span_sync(
        self,
        name: str,
        duration_ms: float,
        attributes: Mapping[str, OTelAttributeValue],
        start_epoch: float,
        end_epoch: float,
    ) -> str:
        tenant_id = str(attributes.get("tenant.id", "default-tenant"))

        # 1. CloudWatch custom latency metric
        cw = self._factory.get_client("cloudwatch")
        cw.put_metric_data(
            Namespace=self.namespace,
            MetricData=[
                {
                    "MetricName": "SpanDurationMs",
                    "Dimensions": [
                        {"Name": "SpanName", "Value": name},
                        {"Name": "TenantId", "Value": tenant_id},
                    ],
                    "Value": float(duration_ms),
                    "Unit": "Milliseconds",
                }
            ],
        )

        # 2. CloudWatch structured log event
        self._ensure_log_stream_sync()
        logs = self._factory.get_client("logs")
        logs.put_log_events(
            logGroupName=self.log_group,
            logStreamName=self._log_stream,
            logEvents=[
                {
                    "timestamp": int(end_epoch * 1000),
                    "message": json.dumps(
                        {
                            "span": name,
                            "duration_ms": round(duration_ms, 2),
                            "attributes": dict(attributes),
                        }
                    ),
                }
            ],
        )

        # 3. AWS X-Ray trace segment
        xray = self._factory.get_client("xray")
        trace_id = f"1-{int(start_epoch):08x}-{secrets.token_hex(12)}"
        segment_id = secrets.token_hex(8)
        segment_doc = json.dumps(
            {
                "name": name.replace(" ", "_"),
                "id": segment_id,
                "trace_id": trace_id,
                "start_time": start_epoch,
                "end_time": end_epoch,
                "annotations": {"tenant_id": tenant_id},
                "metadata": {"attributes": dict(attributes)},
            }
        )
        xray.put_trace_segments(TraceSegmentDocuments=[segment_doc])
        return trace_id

    async def emit_span(
        self,
        name: str,
        duration_ms: float,
        attributes: Mapping[str, OTelAttributeValue],
        start_epoch: Optional[float] = None,
        end_epoch: Optional[float] = None,
    ) -> Optional[str]:
        now = time.time()
        end_ts = end_epoch if end_epoch is not None else now
        start_ts = start_epoch if start_epoch is not None else max(0.0, end_ts - (duration_ms / 1000.0))
        try:
            return await asyncio.to_thread(self._emit_span_sync, name, duration_ms, attributes, start_ts, end_ts)
        except Exception as exc:
            logger.warning("AWS observability emission skipped due to error: %s", exc)
            return None


aws_observability_sink = AWSObservabilitySink()
