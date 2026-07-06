# AGENTS.md — AI Product Studio Agent Guidelines

This file serves as a system-level operational rulebook. Coding assistants and agents working on this project must abide by these rules.

## Core Directives

1. **Strict Monorepo Separation:**
   - Keep `app/` (backend logic) and `frontend/` (Streamlit web client) dependencies separate.
   - Do not cross-import packages from `frontend/` into `app/`, and vice versa.

2. **Data Safety & Git hygiene:**
   - Never commit raw text, CSV, PDF, or binary source files to the git history.
   - Data files must be stored in external buckets. Local development files must be explicitly git-ignored.

3. **Observability Strictness:**
   - Never create custom file-based trace logging mechanisms.
   - Utilize the OpenTelemetry wrapper in `observability/tracer.py` for standard spans.

4. **Async-first standard:**
   - Event loops must not be blocked. Avoid blocking operations (`time.sleep`, synchronous requests) in API routers.
   - Use asynchronous file I/O or `asyncio.to_thread` for blocking system operations.
