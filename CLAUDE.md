# CLAUDE.md - AI Coding Assistant Context

This file details the commands, standards, and architectural guidelines for developers and AI coding assistants working in this repository.

## Commands
* **Run tests:** `poetry run pytest`
* **Run single test:** `poetry run pytest tests/test_retrieval.py`
* **Format code:** `poetry run black app/ tests/`
* **Linter check:** `poetry run ruff check app/`
* **Type checking:** `poetry run mypy app/`
* **Run application locally:** `poetry run uvicorn app.main:app --reload`

## Architecture Structure
This project utilizes a **9-layer production architecture** with strict isolation rules:
1. **API Layer (`app/main.py`, `app/models.py`)**: Request serialization, routing, FastAPI lifespan.
2. **Retrieval Components (`app/components/`)**: Clean retriever and reranker interface implementations.
3. **Core Services (`app/services/`)**: Orchestration pipelines (e.g. `rag_pipeline.py`).
4. **Prompts (`app/prompts/`)**: Prompt templates and centralized registers (supports external hot-swapping).
5. **Agents (`app/agents/`)**: Self-correcting agents, decomposers, and utility tools.
6. **Security Guardrails (`app/security/`)**: Boundary checks for input (injection), context content, and output (hallucination).
7. **Evaluation (`evaluation/`)**: Golden dataset validation and offline evaluators.
8. **Observability (`observability/`)**: Standard OpenTelemetry tracer wrappers.
9. **AI Memory (`.claude/`, `CLAUDE.md`)**: Rules guiding agent actions.

## Coding Style & Patterns
* **Type Annotations:** Python type hints are mandatory (`def query(prompt: str) -> str:`). Do not use `Any`.
* **Async IO:** Always prefer async operations (`async def`) for API routes, database accesses, and downstream HTTP requests (`httpx.AsyncClient`).
* **Error Handling:** Use granular try-except blocks and return appropriate structured HTTP exceptions (FastAPI `HTTPException`) with clean error logs.
* **Imports:** Use absolute imports from root `app` package. Format imports using Ruff/isort.
