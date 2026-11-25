import asyncio
import logging
import time
import uuid
from typing import Dict, List, Optional

from app.cloud.queue_store import dynamodb_state_repo
from app.cloud.secrets import kms_envelope_cipher
from app.cloud.vector_store import S3VectorKnowledgeStore
from app.config import settings
from app.services.connectors.web_scraper import scrape_web_url
from app.services.semantic_cache import semantic_cache
from app.types import JSONDict

logger = logging.getLogger("app.services.ingestion_service")

INGESTION_JOBS: Dict[str, JSONDict] = {}
ACTIVE_COLLECTIONS: Dict[str, JSONDict] = {
    "col-default-openkb": {
        "id": "col-default-openkb",
        "name": "OpenKB Core Knowledge Base",
        "source_type": "vector",
        "uri": "openkb://system-default",
        "chunk_count": 142,
        "tenant_id": "tenant-prod-01",
        "timestamp": "2026-07-24T06:00:00Z",
    }
}


def _use_dynamodb_state() -> bool:
    return bool(settings.aws_backend_enabled and settings.aws_dynamodb_table)


def deterministic_collection_id(job_id: str) -> str:
    """Derive a stable collection identifier from ``job_id`` so SQS retries remain idempotent."""
    suffix = job_id.removeprefix("job-")
    return f"col-{suffix}"


def _build_job_record(
    job_id: str,
    source_type: str,
    uri: str,
    tenant_id: str,
    collection_name: str,
) -> JSONDict:
    return {
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
    }


def create_ingestion_job(source_type: str, uri: str, tenant_id: str, collection_name: str) -> str:
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    INGESTION_JOBS[job_id] = _build_job_record(job_id, source_type, uri, tenant_id, collection_name)
    return job_id


async def create_ingestion_job_async(source_type: str, uri: str, tenant_id: str, collection_name: str) -> str:
    """Create a tenant-scoped ingestion job and persist it to DynamoDB in AWS mode."""
    job_id = create_ingestion_job(source_type, uri, tenant_id, collection_name)
    if _use_dynamodb_state():
        await dynamodb_state_repo.put_ingestion_job(tenant_id, INGESTION_JOBS[job_id])
    return job_id


def get_job_status(job_id: str, tenant_id: str) -> Optional[JSONDict]:
    job = INGESTION_JOBS.get(job_id)
    return job if job and job.get("tenant_id") == tenant_id else None


async def get_job_status_async(job_id: str, tenant_id: str) -> Optional[JSONDict]:
    """Read tenant-scoped ingestion status from DynamoDB in AWS mode, else local memory."""
    if _use_dynamodb_state():
        shared = await dynamodb_state_repo.get_ingestion_job(tenant_id, job_id)
        if shared is not None:
            INGESTION_JOBS[job_id] = shared
            return shared
        return None
    return get_job_status(job_id, tenant_id)


def list_collections(tenant_id: str) -> List[JSONDict]:
    return [col for col in ACTIVE_COLLECTIONS.values() if col.get("tenant_id") == tenant_id]


async def list_collections_async(tenant_id: str) -> List[JSONDict]:
    """List tenant-scoped collections from DynamoDB in AWS mode, else local memory."""
    if _use_dynamodb_state():
        return await dynamodb_state_repo.list_collections(tenant_id)
    return list_collections(tenant_id)


def delete_collection(collection_id: str, tenant_id: str) -> bool:
    collection = ACTIVE_COLLECTIONS.get(collection_id)
    if collection and collection.get("tenant_id") == tenant_id:
        del ACTIVE_COLLECTIONS[collection_id]
        return True
    return False


async def delete_collection_async(collection_id: str, tenant_id: str) -> bool:
    """Delete collection metadata, durable AWS S3/S3 Vectors chunks, and cached answers."""
    collection: Optional[JSONDict] = None
    if _use_dynamodb_state():
        collection = await dynamodb_state_repo.get_collection(tenant_id, collection_id)
    if collection is None:
        local_col = ACTIVE_COLLECTIONS.get(collection_id)
        if local_col is not None:
            if local_col.get("tenant_id") != tenant_id:
                return False
            collection = local_col

    if collection is not None:
        if collection.get("tenant_id") != tenant_id:
            return False
        raw_count = collection.get("chunk_count")
        chunk_count = int(raw_count) if isinstance(raw_count, int) else None
        if settings.aws_backend_enabled:
            vector_store = S3VectorKnowledgeStore(kms_cipher=kms_envelope_cipher)
            try:
                await vector_store.delete_collection_chunks(
                    tenant_id=tenant_id,
                    collection_id=collection_id,
                    chunk_count=chunk_count,
                )
            except Exception:
                # Vectors may already have been deleted before an S3 partial error;
                # always invalidate cached answers even while keeping metadata intact.
                await semantic_cache.invalidate_tenant(tenant_id)
                raise
        if _use_dynamodb_state():
            await dynamodb_state_repo.delete_collection(tenant_id, collection_id)
        ACTIVE_COLLECTIONS.pop(collection_id, None)
        await semantic_cache.invalidate_tenant(tenant_id)
        return True

    if settings.aws_backend_enabled:
        vector_store = S3VectorKnowledgeStore(kms_cipher=kms_envelope_cipher)
        try:
            removed = await vector_store.delete_collection_chunks(
                tenant_id=tenant_id,
                collection_id=collection_id,
            )
        except Exception:
            await semantic_cache.invalidate_tenant(tenant_id)
            raise
        if removed > 0:
            await semantic_cache.invalidate_tenant(tenant_id)
            return True
    return False


async def process_ingestion_job(
    job_id: str,
    content_override: Optional[str] = None,
    *,
    failure_status: str = "failed",
    reconcile_existing: bool = False,
) -> None:
    job = INGESTION_JOBS.get(job_id)
    if not job:
        return

    tenant_id = str(job["tenant_id"])
    try:
        source_type = str(job["source_type"])
        uri = str(job["uri"])
        collection_name = str(job["collection_name"])

        # Step 1: Extract Content
        job["progress"] = 0.25
        if not settings.aws_backend_enabled:
            await asyncio.sleep(0.5)

        if content_override:
            text_content = content_override
        elif source_type == "web":
            text_content = await scrape_web_url(uri)
        else:
            text_content = f"Simulated content extracted from {source_type} source: {uri}"

        # Step 2: Semantic Text Chunking
        job["progress"] = 0.50
        if not settings.aws_backend_enabled:
            await asyncio.sleep(0.5)

        raw_chunks = [p.strip() for p in text_content.split("\n\n") if len(p.strip()) > 20]
        if not raw_chunks:
            raw_chunks = [text_content[i : i + 500] for i in range(0, len(text_content), 500)]

        # Step 3: Embed & Index Chunks in Vector Pipeline
        job["progress"] = 0.75
        if not settings.aws_backend_enabled:
            await asyncio.sleep(0.5)

        indexed_count = len(raw_chunks)
        col_id = str(job.get("collection_id") or deterministic_collection_id(job_id))
        if settings.aws_backend_enabled:
            vector_store = S3VectorKnowledgeStore(kms_cipher=kms_envelope_cipher)
            if reconcile_existing:
                await vector_store.delete_collection_chunks(
                    tenant_id=tenant_id,
                    collection_id=col_id,
                )
            indexed_count = await vector_store.index_chunks(
                tenant_id=tenant_id,
                collection_id=col_id,
                source_uri=uri,
                chunks=raw_chunks,
            )

        # Step 4: Finalize Job & Persist Active Collection
        collection_record: JSONDict = {
            "id": col_id,
            "name": collection_name,
            "source_type": source_type,
            "uri": uri,
            "chunk_count": indexed_count,
            "tenant_id": tenant_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        job["progress"] = 1.0
        job["status"] = "completed"
        job["chunks_processed"] = indexed_count
        job["collection_id"] = col_id
        job["error"] = None

        ACTIVE_COLLECTIONS[col_id] = collection_record
        if _use_dynamodb_state():
            await dynamodb_state_repo.put_collection(tenant_id, collection_record)
        # Invalidate tenant cache BEFORE persisting "completed" so a crash between the two
        # triggers a clean SQS retry rather than acking a completed job with stale caches.
        await semantic_cache.invalidate_tenant(tenant_id)
        if _use_dynamodb_state():
            await dynamodb_state_repo.put_ingestion_job(tenant_id, job)

    except Exception as ex:
        job["status"] = failure_status
        job["error"] = str(ex)
        if _use_dynamodb_state():
            try:
                await dynamodb_state_repo.put_ingestion_job(tenant_id, job)
            except Exception as persist_exc:
                logger.warning("Failed to persist job '%s' failure state to DynamoDB: %s", job_id, persist_exc)
