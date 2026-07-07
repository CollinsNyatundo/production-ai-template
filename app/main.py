import logging
import time
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

# CORS Middlewares
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "env": settings.app_env, "timestamp": time.time()}


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

        # Inject tenant identity into query request context (e.g. for trace and DB isolation)
        logger.info(f"Executing query for tenant '{current_user.tenant_id}' (User: {current_user.username})")

        response = await rag_pipeline.execute(payload)
        latency = (time.perf_counter() - start_time) * 1000.0
        response.latency_ms = latency
        return response
    except Exception as e:
        logger.exception("Error executing query pipeline")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        current_user_context.reset(ctx_token)
