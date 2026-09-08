from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.security.auth import User, get_current_user
from app.services.connectors.file_extractor import extract_file_content
from app.services.ingestion_service import (
    create_ingestion_job,
    delete_collection,
    get_job_status,
    list_collections,
    process_ingestion_job,
)

router = APIRouter(prefix="/api/v1", tags=["Ingestion"])
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class IngestRequest(BaseModel):
    source_type: Literal["web"]
    uri: str
    collection_name: Optional[str] = None


def _require_scope(user: User, scope: str) -> None:
    if scope not in user.scopes:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing required scope: {scope}")


# ── Endpoint 1: JSON body for web / github / sql sources ──────────────────────
@router.post("/ingest")
async def start_ingestion(
    bg_tasks: BackgroundTasks,
    payload: IngestRequest,
    current_user: User = Depends(get_current_user),
):
    """Accept a JSON body describing a URL/GitHub/SQL source to ingest."""
    st_type = payload.source_type
    uri = payload.uri
    _require_scope(current_user, "write")
    t_id = current_user.tenant_id
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
    collection_name: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
):
    """Accept a multipart upload and ingest the file contents."""
    _require_scope(current_user, "write")
    uri = file.filename or "unknown-file"
    c_name = collection_name or f"file-{uri}"
    file_bytes = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(file_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds 5 MiB limit.")
    try:
        content_override = extract_file_content(uri, file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc

    job_id = create_ingestion_job("file", uri, current_user.tenant_id, c_name)
    bg_tasks.add_task(process_ingestion_job, job_id, content_override)

    return {
        "job_id": job_id,
        "status": "processing",
        "message": f"File ingestion job initiated for: {uri}",
    }


@router.get("/ingest/status/{job_id}")
async def check_ingestion_status(job_id: str, current_user: User = Depends(get_current_user)):
    job = get_job_status(job_id, current_user.tenant_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Ingestion job '{job_id}' not found.")
    return job


@router.get("/collections")
async def get_collections(current_user: User = Depends(get_current_user)):
    return {
        "tenant_id": current_user.tenant_id,
        "collections": list_collections(current_user.tenant_id),
    }


@router.delete("/collections/{collection_id}")
async def remove_collection(collection_id: str, current_user: User = Depends(get_current_user)):
    _require_scope(current_user, "write")
    success = delete_collection(collection_id, current_user.tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Collection '{collection_id}' not found.")
    return {"status": "deleted", "collection_id": collection_id}
