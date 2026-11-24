"""SQS ingestion consumer worker for AWS backend mode.

Consumes ingestion jobs from Amazon SQS, hydrates any S3-staged upload text, runs
`process_ingestion_job`, and acknowledges the SQS message ONLY after successful
completion. Failed jobs remain unacknowledged so SQS VisibilityTimeout and native
DLQ RedrivePolicy handle retries and dead-lettering.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.cloud.queue_store import QueuedMessage, SQSIngestionQueue, sqs_ingestion_queue
from app.cloud.secrets import KMSEnvelopeCipher, kms_envelope_cipher
from app.cloud.vector_store import S3VectorKnowledgeStore
from app.services.ingestion_service import INGESTION_JOBS, process_ingestion_job

logger = logging.getLogger("app.services.ingestion_worker")


class SQSIngestionWorker:
    """Async consumer that drains SQS ingestion jobs without blocking the event loop."""

    def __init__(
        self,
        queue: SQSIngestionQueue = sqs_ingestion_queue,
        vector_store: Optional[S3VectorKnowledgeStore] = None,
        kms_cipher: KMSEnvelopeCipher = kms_envelope_cipher,
    ) -> None:
        self._queue = queue
        self._vector_store = vector_store or S3VectorKnowledgeStore(kms_cipher=kms_cipher)

    async def process_message(self, message: QueuedMessage) -> bool:
        """Process a single SQS ingestion message and acknowledge only on success."""
        body = message.body
        job_id = str(body.get("job_id", ""))
        tenant_id = str(body.get("tenant_id", ""))
        source_type = str(body.get("source_type", "file"))
        uri = str(body.get("uri", ""))
        collection_name = str(body.get("collection_name", f"{source_type}-{job_id}"))
        staging_s3_key = str(body.get("staging_s3_key", ""))

        if not job_id or not tenant_id:
            logger.error("SQS message '%s' missing required job_id/tenant_id; leaving for DLQ.", message.message_id)
            return False

        # Ensure job state exists even when processed on a separate worker instance
        if job_id not in INGESTION_JOBS:
            INGESTION_JOBS[job_id] = {
                "job_id": job_id,
                "status": "processing",
                "progress": 0.1,
                "source_type": source_type,
                "uri": uri,
                "tenant_id": tenant_id,
                "collection_name": collection_name,
                "chunks_processed": 0,
                "error": None,
            }

        content_override: Optional[str] = None
        if staging_s3_key:
            try:
                content_override = await self._vector_store.load_staged_text(tenant_id, staging_s3_key)
            except Exception as exc:
                logger.error("Failed to load staged upload '%s' for job '%s': %s", staging_s3_key, job_id, exc)
                INGESTION_JOBS[job_id]["status"] = "failed"
                INGESTION_JOBS[job_id]["error"] = str(exc)
                return False

        await process_ingestion_job(job_id, content_override=content_override)
        job = INGESTION_JOBS.get(job_id)
        if not job or job.get("status") != "completed":
            logger.warning(
                "Ingestion job '%s' did not complete (status=%s); leaving SQS message unacknowledged for retry/DLQ.",
                job_id,
                job.get("status") if job else "missing",
            )
            return False

        await self._queue.acknowledge(message.receipt_handle)
        if staging_s3_key:
            try:
                await self._vector_store.delete_staged_text(staging_s3_key)
            except Exception as cleanup_exc:
                logger.warning("Failed to delete staging key '%s' after ack: %s", staging_s3_key, cleanup_exc)
        return True

    async def process_once(self, max_messages: int = 5, wait_seconds: int = 1) -> int:
        """Poll SQS once and process all received messages. Returns count acknowledged."""
        messages = await self._queue.receive_jobs(max_messages=max_messages, wait_seconds=wait_seconds)
        completed = 0
        for msg in messages:
            if await self.process_message(msg):
                completed += 1
        return completed

    async def run_loop(
        self,
        stop_event: asyncio.Event,
        poll_wait_seconds: int = 2,
        error_backoff_seconds: float = 1.0,
    ) -> None:
        """Continuously poll SQS until `stop_event` is set or task is cancelled."""
        logger.info("SQS ingestion worker loop started.")
        try:
            while not stop_event.is_set():
                try:
                    await self.process_once(max_messages=5, wait_seconds=poll_wait_seconds)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("SQS ingestion worker poll error: %s", exc)
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=error_backoff_seconds)
                    except asyncio.TimeoutError:
                        pass
        except asyncio.CancelledError:
            logger.info("SQS ingestion worker loop cancelled cleanly.")
            raise
        finally:
            logger.info("SQS ingestion worker loop stopped.")


sqs_ingestion_worker = SQSIngestionWorker()


async def _run_standalone() -> None:
    stop_event = asyncio.Event()
    await sqs_ingestion_worker.run_loop(stop_event)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run_standalone())
