"""SQS ingestion consumer worker for AWS backend mode.

Consumes ingestion jobs one-at-a-time from Amazon SQS, enforces idempotent execution
leases via DynamoDB, hydrates S3-staged upload text, runs ``process_ingestion_job``,
and acknowledges the SQS message ONLY after successful completion (or when a duplicate
delivery detects an already-completed job). Non-terminal failures record ``retrying``
status so clients keep polling; terminal failures mark ``failed`` and clean up staged
objects while SQS RedrivePolicy moves the message to the DLQ.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Optional, Tuple

from app.cloud.queue_store import (
    DynamoDBStateRepository,
    QueuedMessage,
    SQSIngestionQueue,
    dynamodb_state_repo,
    sqs_ingestion_queue,
)
from app.cloud.secrets import KMSEnvelopeCipher, kms_envelope_cipher
from app.cloud.vector_store import S3VectorKnowledgeStore
from app.config import settings
from app.services.ingestion_service import (
    INGESTION_JOBS,
    deterministic_collection_id,
    get_job_status_async,
    process_ingestion_job,
)
from app.types import JSONDict

logger = logging.getLogger("app.services.ingestion_worker")


class SQSIngestionWorker:
    """Async consumer that drains SQS ingestion jobs without blocking the event loop."""

    def __init__(
        self,
        queue: SQSIngestionQueue = sqs_ingestion_queue,
        vector_store: Optional[S3VectorKnowledgeStore] = None,
        kms_cipher: KMSEnvelopeCipher = kms_envelope_cipher,
        state_repo: DynamoDBStateRepository = dynamodb_state_repo,
        lease_seconds: int = 30,
        default_max_receive_count: int = 3,
    ) -> None:
        self._queue = queue
        self._vector_store = vector_store or S3VectorKnowledgeStore(kms_cipher=kms_cipher)
        self._state_repo = state_repo
        self._lease_seconds = max(10, lease_seconds)
        self._default_max_receive_count = max(1, default_max_receive_count)
        self._worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        self._last_known_max_receive: Optional[int] = None

    def _use_shared_state(self) -> bool:
        return bool(settings.aws_backend_enabled and settings.aws_dynamodb_table)

    async def _require_readable_redrive_policy(self) -> int:
        """Ensure queue RedrivePolicy is readable before polling SQS for work."""
        max_receive_count = await self._queue.get_max_receive_count()
        if max_receive_count is None:
            raise RuntimeError(
                "SQS queue RedrivePolicy is missing or unreadable; refusing to poll ingestion jobs "
                "until queue attributes and sqs:GetQueueAttributes permission are configured."
            )
        self._last_known_max_receive = max_receive_count
        return max_receive_count

    async def _classify_failure(self, receive_count: int) -> Tuple[str, bool, Optional[int]]:
        """Refresh queue RedrivePolicy on failure so live queue repairs take effect immediately.

        Returns ``(failure_status, should_cleanup_staging, max_receive_count)``:
        - Freshly read policy: classifies ``retrying`` vs ``failed`` and allows staging cleanup
          only on the confirmed terminal attempt (handles live policy changes in both directions).
        - Transiently unreadable policy: never deletes staged uploads prematurely (S3 lifecycle
          expires abandoned uploads after 15 days); uses the last verified policy limit (when
          available) so terminal attempts still transition out of ``retrying`` into ``failed``.
        """
        live_max = await self._queue.get_max_receive_count()
        if live_max is not None:
            self._last_known_max_receive = live_max
            if receive_count < live_max:
                return "retrying", False, live_max
            return "failed", True, live_max
        fallback_max = self._last_known_max_receive
        if fallback_max is not None:
            if receive_count < fallback_max:
                return "retrying", False, fallback_max
            return "failed", False, fallback_max
        return "failed", False, None

    async def _handle_attempt_failure(
        self,
        tenant_id: str,
        job_id: str,
        receive_count: int,
        staging_s3_key: str,
        error_msg: str,
    ) -> None:
        failure_status, should_cleanup_staging, max_receive_count = await self._classify_failure(receive_count)
        INGESTION_JOBS[job_id]["status"] = failure_status
        INGESTION_JOBS[job_id]["error"] = error_msg
        INGESTION_JOBS[job_id]["updated_at"] = time.time()
        if self._use_shared_state():
            try:
                await self._state_repo.put_ingestion_job(tenant_id, INGESTION_JOBS[job_id])
            except Exception as persist_exc:
                logger.warning("Failed to persist job '%s' failure state to DynamoDB: %s", job_id, persist_exc)
        logger.warning(
            "Ingestion job '%s' attempt failed (status=%s, attempt=%d/%s); leaving SQS message unacknowledged.",
            job_id,
            failure_status,
            receive_count,
            max_receive_count if max_receive_count is not None else "unknown",
        )
        if should_cleanup_staging:
            await self._cleanup_staging_best_effort(staging_s3_key)

    async def _cleanup_staging_best_effort(self, staging_s3_key: str) -> None:
        if not staging_s3_key:
            return
        try:
            await self._vector_store.delete_staged_text(staging_s3_key)
        except Exception as cleanup_exc:
            logger.warning("Failed to delete staging key '%s': %s", staging_s3_key, cleanup_exc)

    async def _lease_heartbeat(
        self,
        tenant_id: str,
        job_id: str,
        receipt_handle: str,
        done_event: asyncio.Event,
    ) -> None:
        interval = max(2.0, self._lease_seconds / 2.0)
        while not done_event.is_set():
            try:
                await asyncio.wait_for(done_event.wait(), timeout=interval)
                return
            except asyncio.TimeoutError:
                pass
            try:
                if self._use_shared_state():
                    await self._state_repo.renew_ingestion_lease(
                        tenant_id,
                        job_id,
                        self._worker_id,
                        lease_seconds=self._lease_seconds,
                    )
                await self._queue.extend_visibility(receipt_handle, self._lease_seconds)
            except Exception as renew_exc:
                logger.warning("Lease/visibility renewal failed for job '%s': %s", job_id, renew_exc)

    async def process_message(self, message: QueuedMessage) -> bool:
        """Process a single SQS ingestion message idempotently and acknowledge only on success."""
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

        seed_job: JSONDict = {
            "job_id": job_id,
            "status": "processing",
            "progress": 0.1,
            "source_type": source_type,
            "uri": uri,
            "tenant_id": tenant_id,
            "collection_name": collection_name,
            "collection_id": deterministic_collection_id(job_id),
            "chunks_processed": 0,
            "error": None,
            "updated_at": time.time(),
        }

        # Check completion and claim an active lease BEFORE loading staging or indexing
        if self._use_shared_state():
            claim = await self._state_repo.claim_ingestion_job(
                tenant_id=tenant_id,
                job=seed_job,
                owner_id=self._worker_id,
                lease_seconds=self._lease_seconds,
            )
            if claim == "completed":
                logger.info("Skipping duplicate SQS delivery for already-completed job '%s'.", job_id)
                await self._queue.acknowledge(message.receipt_handle)
                await self._cleanup_staging_best_effort(staging_s3_key)
                return True
            if claim == "in_progress":
                logger.info("Job '%s' already has an active lease on another worker; skipping.", job_id)
                return False
        else:
            existing_local = INGESTION_JOBS.get(job_id)
            if existing_local and existing_local.get("status") == "completed":
                logger.info("Skipping duplicate SQS delivery for completed local job '%s'.", job_id)
                await self._queue.acknowledge(message.receipt_handle)
                await self._cleanup_staging_best_effort(staging_s3_key)
                return True

        INGESTION_JOBS[job_id] = seed_job

        done_event = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            self._lease_heartbeat(tenant_id, job_id, message.receipt_handle, done_event)
        )
        completed_successfully = False
        try:
            content_override: Optional[str] = None
            if staging_s3_key:
                content_override = await self._vector_store.load_staged_text(tenant_id, staging_s3_key)

            await process_ingestion_job(
                job_id,
                content_override=content_override,
                reconcile_existing=message.receive_count > 1,
                raise_on_error=True,
            )
            job = await get_job_status_async(job_id, tenant_id)
            if not job or job.get("status") != "completed":
                error_detail = str(job.get("error") or "ingestion did not complete") if job else "missing job state"
                await self._handle_attempt_failure(
                    tenant_id,
                    job_id,
                    message.receive_count,
                    staging_s3_key,
                    error_detail,
                )
                return False
            completed_successfully = True
        except Exception as exc:
            logger.error("Ingestion attempt error for job '%s': %s", job_id, exc)
            await self._handle_attempt_failure(
                tenant_id,
                job_id,
                message.receive_count,
                staging_s3_key,
                str(exc),
            )
            return False
        finally:
            done_event.set()
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

        if completed_successfully:
            # Handle SQS acknowledgement errors separately so a DeleteMessage failure NEVER
            # overwrites durable "completed" state; redelivery will deduplicate cleanly.
            try:
                await self._queue.acknowledge(message.receipt_handle)
            except Exception as ack_exc:
                logger.warning(
                    "Job '%s' completed durably but SQS acknowledge failed (%s); "
                    "redelivery will deduplicate without re-indexing.",
                    job_id,
                    ack_exc,
                )
                return False
            await self._cleanup_staging_best_effort(staging_s3_key)
            return True
        return False

    async def process_once(self, max_messages: int = 1, wait_seconds: int = 1) -> int:
        """Poll SQS once (default 1 message to avoid visibility starvation) and process received jobs."""
        await self._require_readable_redrive_policy()
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
        """Continuously poll SQS one message at a time until ``stop_event`` is set or task is cancelled."""
        logger.info("SQS ingestion worker loop started (worker_id=%s).", self._worker_id)
        try:
            while not stop_event.is_set():
                try:
                    await self.process_once(max_messages=1, wait_seconds=poll_wait_seconds)
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
