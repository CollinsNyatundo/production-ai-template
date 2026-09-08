# Production AI Reference Template

[![CI](https://github.com/CollinsNyatundo/production-ai-template/actions/workflows/ci.yml/badge.svg)](https://github.com/CollinsNyatundo/production-ai-template/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-10B981.svg)](LICENSE)

A FastAPI and Streamlit reference implementation for experimenting with authenticated, multi-tenant LLM workflows. It demonstrates a ReAct-style tool loop, retrieval adapters, short-term conversation state, in-process memory and caching, tracing hooks, and offline evaluation.

This is a portfolio/reference project, not a deploy-and-forget production platform. The default credentials, local stores, and optional external services must be replaced or hardened before real use.

## What is implemented

| Area | Current implementation |
|---|---|
| API | FastAPI query, streaming, memory, session, and ingestion routes |
| Identity boundary | Demo API-key/JWT authentication; server-derived tenant and user scope |
| Agent workflow | Adaptive routing, query decomposition, bounded tool execution, reranking |
| Retrieval | Optional OpenKB sidecar client plus local tool adapters |
| Model provider | NVIDIA NIM through an OpenAI-compatible async client |
| State | SQLite/PostgreSQL-compatible SQLAlchemy state; process-local cache and memory |
| Safety | Permission-gated tools, input/output filters, scoped ingestion, upload limits, SSRF checks |
| Quality | Pytest, Ruff, mypy, Bandit, migrations, and offline evaluation code |

## Important limitations

- Authentication uses published demo users and API keys. Connect a real identity provider and secret store.
- Cache, ingestion jobs, collections, and memory are process-local; they disappear on restart and do not coordinate replicas.
- OpenKB, NVIDIA NIM, LangSmith, and web search are external/optional dependencies. Their availability and output quality are not guaranteed by this repository.
- The ingestion pipeline stores collection metadata and chunk counts; it does not persist a complete searchable index.
- The Streamlit client is a demonstration UI, not an administrative control plane.
- URL validation reduces common server-side request-forgery paths, but production egress controls and DNS-aware network policy are still required.

## Request boundary

The API ignores caller-supplied tenant, user, permission, and session scope where identity matters. Those values are derived from the authenticated principal. Ingestion status, collection listing/deletion, query cache entries, memories, and conversation sessions are tenant-scoped.

## Local setup

```bash
git clone https://github.com/CollinsNyatundo/production-ai-template.git
cd production-ai-template
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
PYTHONPATH=. python scripts/migrate.py upgrade
uvicorn app.main:app --reload
```

For live model calls, set `NVIDIA_API_KEY`. The default development mode permits an anonymous local developer identity; any non-development environment requires authentication and rejects the published JWT secret.

Example local request:

```bash
curl -X POST http://127.0.0.1:8000/api/query \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: api-key-user-54321' \
  -d '{"query":"Summarize the retrieval flow","session_id":"demo-1"}'
```

Docker Compose starts the API, Streamlit client, and Redis container on loopback. Redis is reserved for a future shared cache and is not used by the current semantic-cache implementation.

```bash
docker compose up --build
```

## Verification

```bash
pip install -r requirements-dev.txt
ruff check .
ruff format --check .
mypy app evaluation observability scripts tests
bandit -r app -ll -ii
pytest --cov=app --cov-fail-under=75
PYTHONPATH=. python scripts/migrate.py upgrade
```

The normal test suite mocks or bypasses external services and does not require production API keys.

## Repository map

```text
app/api/                    HTTP ingestion routes
app/agents/                 routing, execution, and tool registry
app/components/             retrieval and reranking adapters
app/security/               authentication, filters, resilience
app/services/               RAG pipeline, state, memory, cache, connectors
evaluation/                 offline evaluation and trajectory logging
frontend/                   Streamlit demonstration client
observability/              OpenTelemetry and cost tracking helpers
tests/                      isolated automated tests
```

## License

[MIT](LICENSE)
