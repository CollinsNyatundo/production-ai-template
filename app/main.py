from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import time
import logging

from app.config import settings
from app.models import QueryRequest, QueryResponse
from app.services.rag_pipeline import rag_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize components (e.g. database connections, cache warmups)
    logger.info("Initializing application services...")
    # Redis cache connection check could go here
    yield
    # Cleanup resources
    logger.info("Shutting down application services...")

app = FastAPI(
    title="Production AI Core API",
    description="A modular 9-layer AI/RAG system template API.",
    version="1.0.0",
    lifespan=lifespan
)

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
    return {
        "status": "healthy",
        "env": settings.app_env,
        "timestamp": time.time()
    }

@app.post("/api/query", response_model=QueryResponse)
async def query_endpoint(payload: QueryRequest):
    start_time = time.perf_counter()
    try:
        response = await rag_pipeline.execute(payload)
        latency = (time.perf_counter() - start_time) * 1000.0
        response.latency_ms = latency
        return response
    except Exception as e:
        logger.exception("Error executing query pipeline")
        raise HTTPException(status_code=500, detail=str(e))
