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
* **Type Annotations:** Python type hints are mandatory (`def query(prompt: str) -> str:`). **`Any` is banned outright - no exceptions, including `Dict[str, Any]`, `List[Any]`, bare untyped `Callable`, and unannotated `**kwargs`.** This is enforced by `mypy --strict`-adjacent config in CI (`.github/workflows/ci.yml`), not just a style preference - a PR that introduces `Any` should fail review even if CI doesn't catch every case. Use, in order of preference:
  - A specific type or `Union` of the concrete types actually possible.
  - `TypedDict` for a dict with a known, fixed shape (see `app/types.py` for the project's shared ones: `ChatMessage`, `AgentTrajectoryStep`, `AgentExecutionResult`, etc. - reuse these instead of inventing new ad-hoc dicts).
  - `object` (not `Any`) when a value is genuinely arbitrary and unused beyond passthrough (e.g. `**kwargs` forwarded to an event subscriber) - `object` still forces callers to narrow before doing anything type-specific with it, which is the entire point.
  - `TypeVar`/`ParamSpec` for generic wrapper functions that preserve a wrapped callable's real signature (see `AsyncCircuitBreaker.call` in `app/security/resilience.py`).
  - A recursive `TypeAliasType` (from `typing_extensions`, not a plain self-referential `Union`) for genuinely arbitrary JSON, e.g. tool call arguments (see `JSONValue` in `app/types.py`). Plain recursive `Union` aliases type-check fine under mypy but crash pydantic with `RecursionError` when it tries to build a runtime validation schema from them - use `TypeAliasType` specifically when the value will ever appear in a pydantic model field, not just a plain function signature.
  - A narrow, single-line `# type: ignore[<code>]` with a comment explaining why, reserved for genuine third-party SDK boundary friction (e.g. calling `openai`'s `create()` with our own looser internal TypedDict shape) - never as a substitute for typing our own code.
* **Async IO:** Always prefer async operations (`async def`) for API routes, database accesses, and downstream HTTP requests (`httpx.AsyncClient`).
* **Error Handling:** Use granular try-except blocks and return appropriate structured HTTP exceptions (FastAPI `HTTPException`) with clean error logs.
* **Imports:** Use absolute imports from root `app` package. Format imports using Ruff/isort.
