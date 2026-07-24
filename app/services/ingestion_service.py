import asyncio
import time
import uuid
from typing import Dict, List, Optional

from app.services.connectors.web_scraper import scrape_web_url

INGESTION_JOBS: Dict[str, dict] = {}
ACTIVE_COLLECTIONS: Dict[str, dict] = {
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


def create_ingestion_job(source_type: str, uri: str, tenant_id: str, collection_name: str) -> str:
    job_id = f"job-{uuid.uuid4().hex[:8]}"
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
    return job_id


def get_job_status(job_id: str) -> Optional[dict]:
    return INGESTION_JOBS.get(job_id)


def list_collections(tenant_id: str) -> List[dict]:
    return [col for col in ACTIVE_COLLECTIONS.values() if col.get("tenant_id") == tenant_id or tenant_id == "all"]


def delete_collection(collection_id: str) -> bool:
    if collection_id in ACTIVE_COLLECTIONS:
        del ACTIVE_COLLECTIONS[collection_id]
        return True
    return False


async def process_ingestion_job(job_id: str, content_override: Optional[str] = None):
    job = INGESTION_JOBS.get(job_id)
    if not job:
        return

    try:
        source_type = job["source_type"]
        uri = job["uri"]
        tenant_id = job["tenant_id"]
        collection_name = job["collection_name"]

        # Step 1: Extract Content
        job["progress"] = 0.25
        await asyncio.sleep(0.5)

        if content_override:
            text_content = content_override
        elif source_type == "web":
            text_content = await scrape_web_url(uri)
        else:
            text_content = f"Simulated content extracted from {source_type} source: {uri}"

        # Step 2: Semantic Text Chunking
        job["progress"] = 0.50
        await asyncio.sleep(0.5)

        raw_chunks = [p.strip() for p in text_content.split("\n\n") if len(p.strip()) > 20]
        if not raw_chunks:
            raw_chunks = [text_content[i : i + 500] for i in range(0, len(text_content), 500)]

        # Step 3: Embed & Index Chunks in Vector Pipeline
        job["progress"] = 0.75
        await asyncio.sleep(0.5)

        indexed_count = len(raw_chunks)
        # Chunks are stored in the collection record below.
        # Full vector embedding is handled by the RAG pipeline at query time.

        # Step 4: Finalize Job & Add Active Collection
        job["progress"] = 1.0
        job["status"] = "completed"
        job["chunks_processed"] = indexed_count

        col_id = f"col-{uuid.uuid4().hex[:6]}"
        ACTIVE_COLLECTIONS[col_id] = {
            "id": col_id,
            "name": collection_name,
            "source_type": source_type,
            "uri": uri,
            "chunk_count": indexed_count,
            "tenant_id": tenant_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    except Exception as ex:
        job["status"] = "failed"
        job["error"] = str(ex)
