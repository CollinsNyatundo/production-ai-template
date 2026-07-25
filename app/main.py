import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.ingest import router as ingest_router
from app.components.openkb_client import openkb_client
from app.config import settings
from app.models import QueryRequest, QueryResponse
from app.security.auth import User, get_current_user
from app.services.conversation import conversation_service
from app.services.hooks import lifecycle_hooks
from app.services.rag_pipeline import rag_pipeline
from app.services.state_store import state_store
from observability.tracer import current_user_context

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing application services...")
    await state_store.initialize_tables()
    yield
    logger.info("Shutting down application services...")


app = FastAPI(
    title="Production AI Core API",
    description="A modular 9-layer AI/RAG system template API.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(ingest_router)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, cast(Any, _rate_limit_exceeded_handler))

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "env": settings.app_env, "timestamp": time.time()}


def _scoped_session_id(current_user: User, session_id: str) -> str:
    return f"{current_user.tenant_id}:{session_id}"


@app.delete("/api/session/{session_id}")
@limiter.limit(f"{settings.rate_limit_calls}/{settings.rate_limit_period} seconds")
async def clear_session_endpoint(
    session_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    scoped_id = _scoped_session_id(current_user, session_id)
    logger.info(f"Clearing session {session_id} for user {current_user.username}")
    await conversation_service.clear_history(scoped_id)
    return {"status": "cleared", "session_id": session_id}


@app.post("/api/query", response_model=QueryResponse)
@limiter.limit(f"{settings.rate_limit_calls}/{settings.rate_limit_period} seconds")
async def query_endpoint(
    payload: QueryRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    start_time = time.perf_counter()
    ctx_token = current_user_context.set(
        {
            "username": current_user.username,
            "role": current_user.role,
            "tenant_id": current_user.tenant_id,
            "app_env": settings.app_env,
        }
    )

    try:
        payload.actor_permission = current_user.permission_level
        client_session_id = payload.session_id
        payload.session_id = _scoped_session_id(current_user, payload.session_id)

        logger.info(f"Executing query for tenant {current_user.tenant_id}")

        response = await rag_pipeline.execute(payload)
        response.latency_ms = (time.perf_counter() - start_time) * 1000.0
        payload.session_id = client_session_id
        return response
    except Exception:
        error_id = uuid.uuid4().hex[:12]
        logger.exception(f"Error executing query pipeline (error_id={error_id})")
        raise HTTPException(
            status_code=500,
            detail=f"An internal error occurred. Reference: {error_id}",
        )
    finally:
        current_user_context.reset(ctx_token)


@app.get("/api/memory")
async def get_memories_endpoint(
    tenant_id: str = "default-tenant",
    user_id: str = "default-user",
    current_user: User = Depends(get_current_user),
):
    """Retrieves active persistent memories for tenant and user."""
    from app.services.memory import mem0_client

    tid = current_user.tenant_id if current_user else tenant_id
    uid = current_user.username if current_user else user_id
    memories = await mem0_client.get_all_memories(tenant_id=tid, user_id=uid)
    return {"status": "success", "tenant_id": tid, "user_id": uid, "memories": memories}


@app.delete("/api/memory/{memory_id}")
async def delete_memory_endpoint(
    memory_id: str,
    tenant_id: str = "default-tenant",
    user_id: str = "default-user",
    current_user: User = Depends(get_current_user),
):
    """Deletes a specific persistent memory item."""
    from app.services.memory import mem0_client

    tid = current_user.tenant_id if current_user else tenant_id
    uid = current_user.username if current_user else user_id
    deleted = await mem0_client.delete_memory(tenant_id=tid, user_id=uid, memory_id=memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory item not found.")
    return {"status": "success", "deleted_memory_id": memory_id}


@limiter.limit(f"{settings.rate_limit_calls}/{settings.rate_limit_period} seconds")
async def query_stream_endpoint(
    payload: QueryRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    scoped_id = _scoped_session_id(current_user, payload.session_id)

    async def sse_generator():
        try:
            async for chunk in openkb_client.query_stream(payload.query, session_id=scoped_id):
                await lifecycle_hooks.emit("on_llm_new_token", token=chunk)
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Error streaming from OpenKB: {e}")
            yield f'data: {{"error": "{str(e)}"}}\n\n'

    return StreamingResponse(sse_generator(), media_type="text/event-stream")
