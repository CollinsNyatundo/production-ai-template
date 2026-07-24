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

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **production-ai-template** (932 symbols, 1456 relationships, 23 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> Index stale? Run `node .gitnexus/run.cjs analyze` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? `npx gitnexus analyze` (npm 11 crash → `npm i -g gitnexus`; #1939).

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows. For regression review, compare against the default branch: `detect_changes({scope: "compare", base_ref: "main"})`.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `query({search_query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `context({name: "symbolName"})`.
- For security review, `explain({target: "fileOrSymbol"})` lists taint findings (source→sink flows; needs `analyze --pdg`).

## Never Do

- NEVER edit a function, class, or method without first running `impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit changes without running `detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/production-ai-template/context` | Codebase overview, check index freshness |
| `gitnexus://repo/production-ai-template/clusters` | All functional areas |
| `gitnexus://repo/production-ai-template/processes` | All execution flows |
| `gitnexus://repo/production-ai-template/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
