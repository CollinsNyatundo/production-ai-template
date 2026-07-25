from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.services.connectors.file_extractor import extract_file_content
from app.services.ingestion_service import (
    create_ingestion_job,
    delete_collection,
    get_job_status,
    list_collections,
    process_ingestion_job,
)

router = APIRouter(prefix="/api/v1", tags=["Ingestion"])


class IngestRequest(BaseModel):
    source_type: str  # "web", "github", "file", "sql"
    uri: str
    tenant_id: str = "tenant-prod-01"
    collection_name: Optional[str] = None


# ── Endpoint 1: JSON body for web / github / sql sources ──────────────────────
@router.post("/ingest")
async def start_ingestion(
    bg_tasks: BackgroundTasks,
    payload: IngestRequest,
):
    """Accept a JSON body describing a URL/GitHub/SQL source to ingest."""
    st_type = payload.source_type
    uri = payload.uri
    t_id = payload.tenant_id
    c_name = payload.collection_name or f"{st_type}-{uri.split('/')[-1]}"

    job_id = create_ingestion_job(st_type, uri, t_id, c_name)
    bg_tasks.add_task(process_ingestion_job, job_id, None)

    return {
        "job_id": job_id,
        "status": "processing",
        "message": f"Ingestion job initiated for {st_type} source: {uri}",
    }


# ── Endpoint 2: Multipart form + file upload ──────────────────────────────────
@router.post("/ingest/upload")
async def start_file_ingestion(
    bg_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source_type: str = Form("file"),
    tenant_id: str = Form("tenant-prod-01"),
    collection_name: Optional[str] = Form(None),
):
    """Accept a multipart upload and ingest the file contents."""
    uri = file.filename or "unknown-file"
    c_name = collection_name or f"file-{uri}"
    file_bytes = await file.read()
    content_override = extract_file_content(uri, file_bytes)

    job_id = create_ingestion_job(source_type, uri, tenant_id, c_name)
    bg_tasks.add_task(process_ingestion_job, job_id, content_override)

    return {
        "job_id": job_id,
        "status": "processing",
        "message": f"File ingestion job initiated for: {uri}",
    }


@router.get("/ingest/status/{job_id}")
async def check_ingestion_status(job_id: str):
    job = get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Ingestion job '{job_id}' not found.")
    return job


@router.get("/collections")
async def get_collections(tenant_id: str = "tenant-prod-01"):
    return {
        "tenant_id": tenant_id,
        "collections": list_collections(tenant_id),
    }


@router.delete("/collections/{collection_id}")
async def remove_collection(collection_id: str):
    success = delete_collection(collection_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Collection '{collection_id}' not found.")
    return {"status": "deleted", "collection_id": collection_id}
