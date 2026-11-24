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
| Retrieval | Optional OpenKB sidecar client, tenant-isolated AWS S3 Vectors store (`AWS_BACKEND_ENABLED=true`), and local fallback |
| Model provider | NVIDIA NIM through an OpenAI-compatible async client |
| State | SQLite/PostgreSQL SQLAlchemy state, optional DynamoDB multi-tenant feedback/state, and SQS DLQ queue adapters |
| Safety | Permission-gated tools, input/output filters, KMS tenant `EncryptionContext`, Secrets Manager JWT resolution, scoped ingestion, upload limits, SSRF checks |
| Quality | Pytest, Ruff, mypy, Bandit, migrations, offline evaluation, and live zero-mock `aws/aws-emulator` CI integration |

## Important limitations

- Authentication uses published demo users and API keys. Enable `AWS_BACKEND_ENABLED=true` to pull JWT signing secrets from AWS Secrets Manager, and connect a real identity provider before production use.
- Default cache, ingestion jobs, collections, and memory are process-local; enabling `AWS_BACKEND_ENABLED=true` persists documents to S3 (with KMS envelope encryption), embeddings to per-tenant Amazon S3 Vectors indices, feedback to DynamoDB, and spans to CloudWatch/X-Ray.
- OpenKB, NVIDIA NIM, LangSmith, and web search are external/optional dependencies. Their availability and output quality are not guaranteed by this repository.
- Offline/CI vector indexing uses a deterministic 64-dim feature-hashing embedder so S3 Vectors tests run reproducibly without external embedding keys; swap in NVIDIA NIM embeddings for production semantic recall.
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

## AWS Cloud-Native Local Profile (`aws/aws-emulator`)

You can run and integration-test the full 7-service AWS cloud-native backend locally or in CI at **$0** (no AWS account required) using [`aws/aws-emulator`](https://github.com/aws/aws-emulator):

- **Amazon S3 + S3 Vectors**: tenant-prefixed document archival and per-tenant vector index isolation (`app/cloud/vector_store.py`)
- **AWS KMS + Secrets Manager**: tenant-bound `EncryptionContext={"tenant_id": ...}` envelope encryption and runtime JWT secret lookup (`app/cloud/secrets.py`)
- **Amazon SQS (with native DLQ `RedrivePolicy`) + DynamoDB**: async ingestion queue and tenant-partitioned durable feedback (`app/cloud/queue_store.py`)
- **CloudWatch Metrics, CloudWatch Logs & X-Ray**: real span latency metrics, structured logs, and trace segments (`app/cloud/telemetry.py`)

```bash
# 1. Build and start aws-emulator locally (telemetry off, ~200 MiB RAM, ~1s cold start)
docker buildx build --load -t aws-emulator:local -f Dockerfile.aws-emulator .
mkdir -p ~/.aws/emulator
docker run -d --rm --name aws-emulator --memory=2g --memory-swap=2g --cap-drop=ALL \
  -p 127.0.0.1:9297:9297 -v "$HOME/.aws/emulator:/home/emulator/.aws/emulator" \
  aws-emulator:local -p 9297

# 2. Point AWS SDKs at the emulator and bootstrap all 7 services idempotently
export AWS_ENDPOINT_URL=https://127.0.0.1:9297
export AWS_SHARED_CREDENTIALS_FILE=$HOME/.aws/emulator/9297/emulator_credentials
export AWS_CONFIG_FILE=$HOME/.aws/emulator/9297/config
export AWS_CA_BUNDLE=$HOME/.aws/emulator/9297/ca.pem
export AWS_EC2_METADATA_DISABLED=true
export AWS_DISABLE_HOST_PREFIX_INJECTION=true
export AWS_REGION=us-east-1
PYTHONPATH=. python scripts/bootstrap_aws_emulator.py --format env

# 3. Run the zero-mock live integration suite
pytest -m aws_emulator -v
```

## Verification

```bash
pip install -r requirements-dev.txt
ruff check .
ruff format --check .
mypy app evaluation observability scripts tests
bandit -r app -ll -ii
pytest -m "not aws_emulator" --cov=app --cov-fail-under=75
PYTHONPATH=. python scripts/migrate.py upgrade
```

The default unit test suite mocks or bypasses external services and requires no cloud credentials; the `aws-emulator-integration` CI job runs `pytest -m aws_emulator -v` against a live `aws/aws-emulator` container with zero mocks.

## Repository map

```text
app/api/                    HTTP ingestion routes
app/agents/                 routing, execution, and tool registry
app/cloud/                  optional AWS adapters (S3 Vectors, KMS, Secrets Manager, SQS, DynamoDB, CloudWatch/X-Ray)
app/components/             retrieval and reranking adapters
app/security/               authentication, filters, resilience
app/services/               RAG pipeline, state, memory, cache, connectors
evaluation/                 offline evaluation and trajectory logging
frontend/                   Streamlit demonstration client
observability/              OpenTelemetry, CloudWatch/X-Ray, feedback, and cost tracking helpers
scripts/                    database migrations and AWS Emulator bootstrapper
tests/                      isolated unit tests and live aws_emulator integration tests
```

## License

[MIT](LICENSE)
