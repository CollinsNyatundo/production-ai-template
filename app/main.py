import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

# SlowAPI imports for Rate Limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.models import QueryRequest, QueryResponse
from app.security.auth import User, get_current_user
from app.services.conversation import conversation_service
from app.services.rag_pipeline import rag_pipeline
from app.services.state_store import state_store
from observability.tracer import current_user_context

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

# Initialize SlowAPI Limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize components
    logger.info("Initializing application services...")
    # Initialize SQLAlchemy database tables (PostgreSQL/SQLite)
    await state_store.initialize_tables()
    yield
    # Cleanup resources
    logger.info("Shutting down application services...")


app = FastAPI(
    title="Production AI Core API",
    description="A modular 9-layer AI/RAG system template API.",
    version="1.0.0",
    lifespan=lifespan,
)

# Wire Limiter state and exception handlers
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# CORS Middleware - explicit origin allow-list. allow_origins=["*"] combined with
# allow_credentials=True is a known misconfiguration: Starlette reflects the
# request's actual Origin header back rather than sending a literal "*" in that
# combination, which means any site can make credentialed cross-origin requests.
# (See CVE-2026-32610 for a recent real-world instance of exactly this pattern.)
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
    """
    Prefixes the client-supplied session_id with the authenticated caller's
    tenant_id before it ever reaches conversation_service/state_store/
    agent_executor. Closes a real gap: previously any authenticated caller
    could read or clear any session_id they knew or guessed, since the raw
    client-supplied string was used directly as the storage key with no
    ownership check. tenant_id comes from the verified JWT/API-key identity
    (see app/security/auth.py), not from client input, so a caller can't
    forge access to another tenant's sessions by guessing this prefix -
    they'd need a valid credential for that tenant, which is the actual
    security boundary here.

    This scopes by tenant, not by individual user - anyone with valid
    credentials for the same tenant shares session access, which matches how
    tenant_id is used elsewhere in this codebase (e.g. OTel span tagging).
    Scoping to individual users instead would be a one-line change
    (f"{current_user.tenant_id}:{current_user.username}:{session_id}") if
    that's the isolation model you actually want.
    """
    return f"{current_user.tenant_id}:{session_id}"


@app.delete("/api/session/{session_id}")
@limiter.limit(f"{settings.rate_limit_calls}/{settings.rate_limit_period} seconds")
async def clear_session_endpoint(
    session_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    scoped_id = _scoped_session_id(current_user, session_id)
    logger.info(f"Clearing session '{session_id}' (scoped: '{scoped_id}') for user '{current_user.username}'")
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

    # Propagate tenant context to OpenTelemetry spans via contextvars
    ctx_token = current_user_context.set(
        {
            "username": current_user.username,
            "role": current_user.role,
            "tenant_id": current_user.tenant_id,
            "app_env": settings.app_env,
        }
    )

    try:
        # Override user-input permission with authenticated permission level (Server-Side Gating)
        payload.actor_permission = current_user.permission_level

        # Scope session storage to the authenticated tenant server-side (see
        # _scoped_session_id docstring) - the client-facing session_id string
        # is unchanged in the response, only the internal storage key differs.
        client_session_id = payload.session_id
        payload.session_id = _scoped_session_id(current_user, payload.session_id)

        logger.info(f"Executing query for tenant '{current_user.tenant_id}' (User: {current_user.username})")

        response = await rag_pipeline.execute(payload)
        response.latency_ms = (time.perf_counter() - start_time) * 1000.0
        # Return the client's original session_id, not our internal scoped key
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
