# Product Requirements Document (PRD): Production AI Template

## 1. Summary

This document specifies the product requirements for **Production AI Template**, an enterprise-ready, resilient, and multi-tenant LLM agent backend framework. Built on FastAPI, NVIDIA NIM embeddings (`nvidia/nv-embedqa-e5-v5`), and OpenKB sidecar hybrid retrieval, this product bridges the gap between prototype LLM scripts and mission-critical production AI infrastructure.

---

## 2. Contacts

| Contact Name | Role | Responsibilities / Context |
| :--- | :--- | :--- |
| **Collins Nyatundo** | Lead AI Systems Architect & Maintainer | Product vision, core architecture, and open-source release |
| **Engineering Team** | Core Backend & DevSecOps | ReAct loop execution, circuit breaker resilience, and CI pipeline |
| **Security & Compliance** | Security Auditor | Multi-tenant session isolation, JWT validation, PII redaction |

---

## 3. Background

### Context
Building LLM applications is fast, but taking them to production is difficult. Most existing templates rely on simplistic single-threaded scripts, swallow errors silently, lack tenant isolation, or hardcode generic mocks.

### Why Now?
In 2025–2026, enterprise adoption of agentic AI requires strict infrastructure controls:
- **Resilience**: LLMs and third-party tools fail frequently. Systems must degrade gracefully without crashing.
- **Type Safety**: Unchecked `Any` types in Python cause silent runtime crashes during streaming responses.
- **Data Privacy & Multi-Tenancy**: Data leakage across tenants is a critical security violation.

### What Just Became Possible?
With the advent of low-latency NVIDIA NIM microservices, specialized sidecars like OpenKB, and formal agent harness taxonomies $\mathcal{H} = (E, T, C, S, L, V)$, developers can now build self-healing, type-safe agent backends that operate reliably under load.

---

## 4. Objective

### Strategic Intent
Provide software teams with a zero-config, production-tested AI backend foundation that eliminates repetitive architectural boilerplate (auth, resilience, state, observability, quality evaluation).

### SMART Key Results (OKRs)
- **KR1 (Quality & Recall)**: Achieve $\ge 90\%$ concept recall on benchmark RAG evaluation datasets.
- **KR2 (Resilience)**: Achieve $99.9\%$ backend uptime by isolating failing tool integrations via `AsyncCircuitBreaker`.
- **KR3 (Type Safety)**: Maintain $100\%$ `mypy` strict compliance with zero implicit or explicit `Any` types across the codebase.
- **KR4 (Latency)**: Maintain P95 query response time under $3.0$ seconds for non-streaming calls.

---

## 5. Market Segment(s)

### Target Audience
1. **Fintech & Enterprise AI Engineers**: Teams building customer-facing financial or technical assistance agents requiring strict auditability and zero data leakage.
2. **AI Product Studios & Agencies**: Developers needing a standard, repeatable template to launch production AI backends in days rather than months.
3. **Platform & DevSecOps Engineers**: Engineers enforcing strict CI/CD linting, secret scanning, and OpenTelemetry observability.

### User Jobs-To-Be-Done (JTBD)
- *When* I am building a customer-facing AI agent, *I want* pre-built resilience, authentication, and state management, *so I can* focus purely on domain logic without reinventing backend safety infrastructure.

---

## 6. Value Proposition(s)

### Customer Gains
- **Instant Production-Readiness**: Out-of-the-box support for JWT auth, database migrations, and OpenTelemetry spans.
- **Zero Silent Failures**: Asynchronous circuit breakers gracefully fallback when upstream APIs (OpenKB, web search, LLM endpoints) experience outages.
- **Continuous Quality Assurance**: Built-in evaluation pipeline ([offline_eval.py](file:///d:/Projects/ai_template/evaluation/offline_eval.py)) prevents prompt drift during updates.

### Pains Avoided
- **No Data Leakage**: Session IDs are automatically isolated server-side by tenant (`tenant_id:session_id`).
- **No Type Debt**: Zero `Any` enforcement prevents mysterious runtime `AttributeError` and `KeyError` crashes in production.
- **No Unbounded Cost Spikes**: Context window token budgeting prevents runaway token bills.

---

## 7. Solution Specification

### 7.1 Architecture & UX Workflows
The backend is structured around a **9-Layer Architecture** and the $\mathcal{H} = (E, T, C, S, L, V)$ harness taxonomy:

```
FastAPI Entrypoint (L1) 
  ↳ Auth & Tenant Isolation (L7) 
    ↳ Resilience Circuit Breaker (L7) 
      ↳ ReAct Execution Loop (E - L6) 
        ↳ OpenKB Hybrid Retriever (L2) 
          ↳ NVIDIA NIM Embeddings (L3) 
```

### 7.2 Key System Features

#### Feature 1: ReAct Agent Execution Loop (E)
- **Module**: `app/agents/executor.py`
- **Behavior**: LLM inspects active tool schemas each turn. If a tool fails, the `AsyncCircuitBreaker` traps the exception and returns an observation error string, allowing the LLM turn to continue alternative reasoning paths.

#### Feature 2: Hybrid OpenKB Sidecar Retrieval
- **Module**: `app/components/hybrid_retriever.py` & `app/components/openkb_client.py`
- **Behavior**: Merges dense vector representations (`nvidia/nv-embedqa-e5-v5`) and sparse keyword BM25 search. Scores are reranked via a single batched LLM call (`app/components/reranker.py`).

#### Feature 3: Strict Static Type System
- **Module**: `app/types.py`
- **Behavior**: Custom TypedDicts for `ChatMessage`, `ToolSchema`, and API payloads. Enforced by `mypy` in CI with `disallow_any_generics` and `warn_return_any`.

#### Feature 4: Async Circuit Breakers
- **Module**: `app/security/resilience.py`
- **Behavior**: Lock-guarded state transitions (`CLOSED`, `OPEN`, `HALF_OPEN`). Ensures a single recovery probe tests an endpoint when recovering.

### 7.3 Technology Stack
- **Language & Runtime**: Python 3.11+
- **API Framework**: FastAPI & Uvicorn (SSE streaming support)
- **LLM Endpoint**: NVIDIA NIM (`meta/llama-3.1-70b-instruct`) via OpenAI SDK
- **Embedding Model**: NVIDIA NIM (`nvidia/nv-embedqa-e5-v5`)
- **Knowledge Base**: OpenKB Sidecar Client
- **Database & ORM**: Async SQLAlchemy (SQLite local / PostgreSQL production) + Alembic
- **Observability**: OpenTelemetry + LangSmith + Prometheus

### 7.4 Key Assumptions & Risks
- **Assumption 1**: Downstream services (OpenKB, NVIDIA NIM) provide REST/HTTP interfaces.
- **Risk 1**: Upstream API rate limits on free-tier LLM endpoints during batch evaluation.
  - *Mitigation*: Implemented automatic 5x retry backoff on `AsyncOpenAI` client and paced evaluation loop steps.

---

## 8. Release Planning & Roadmap

```
[Phase 1: Core Harness] ──> [Phase 2: OpenKB & NIM Integrations] ──> [Phase 3: Production Scale]
      (Completed)                     (Completed - Current)                 (Future Roadmap)
```

### Phase 1: Core Foundation (Completed)
- FastAPI entrypoint with SSE streaming.
- Async SQLAlchemy state store & Alembic migrations.
- Base ReAct agent executor & tool registry.

### Phase 2: Hybrid Sidecar & Enterprise Resilience (Current Version)
- OpenKB sidecar integration for hybrid BM25 + dense retrieval.
- NVIDIA NIM `nv-embedqa-e5-v5` embedding pipeline.
- `AsyncCircuitBreaker` lock-guarded isolation for tools and LLMs.
- Zero-`Any` mypy static typing compliance.
- Automated trajectory concept recall evaluation pipeline.

### Phase 3: Scaling & Advanced Enterprise Features (Future)
- **Redis-Backed Semantic Cache**: Upgrade in-process cache to distributed Redis cluster.
- **Multi-Vector Retrieval**: Support image & unstructured document chunking.
- **Granular RBAC**: Dynamic tool permission levels per JWT user scope.
