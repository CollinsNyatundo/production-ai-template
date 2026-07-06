# Production-Ready AI Application Template

This repository represents a robust, enterprise-ready template for building scalable, secure, and observable AI/LLM-based applications. It is based on a modern 9-layer AI application architecture, modified to address and mitigate common architectural anti-patterns found in typical prototypes.

## 🏗️ 9-Layer Architecture Overview

The codebase is organized into 9 isolated, modular layers:

```
production-ai-template/
├── .claude/                  # Layer 9: AI Coding Agent Rules & Context
│   └── rules/                
│       ├── code-style.md     
│       └── testing.md        
├── app/                      
│   ├── components/           # Layer 2: Custom Retrieval Components (Hybrid search, Rerankers)
│   ├── services/             # Layer 3: Core Orchestration (Pipelines, Caches, Routers)
│   ├── prompts/              # Layer 5: Dynamic Prompts & Registry
│   ├── agents/               # Layer 6: Agentic Intelligence & Tools
│   ├── security/             # Layer 7: Guardrails (Input, Content, Output Filters)
│   ├── main.py               # Layer 1: Core API Entrypoint (FastAPI)
│   ├── config.py             
│   ├── models.py             
│   └── Dockerfile            
├── evaluation/               # Layer 8: Evaluation Framework (Offline & Monitoring)
│   ├── golden_dataset.json   
│   ├── offline_eval.py       
│   └── online_monitor.py     
├── observability/            # Layer 9: Observability Stack (Tracing, Cost, Feedback)
│   ├── tracer.py             
│   ├── feedback.py           
│   └── cost_tracker.py       
├── data/                     # External Data Ingestion Configs (Ignored raw files)
├── scripts/                  # DB migrations, seeding, healthchecks
├── frontend/                 # Separately containerized Streamlit web interface
└── tests/                    # CI-Ready unit & integration tests
```

---

## 🛠️ Pitfalls Mitigated (Architectural Enhancements)

In transitioning from an "infographic" layout to real-world cloud engineering, this template addresses several critical design flaws:

### 1. Data Registry vs. Git Bloat
* **The Pitfall:** Checking raw datasets (`data/raw/`) directly into Git, which leads to massive repository sizes and slow operations.
* **Mitigation:** The `.gitignore` strictly blocks all binary and source documents under `data/raw/` and `data/processed/`. The `data/` folder is reserved strictly for schema descriptions and index configs. Real data pipelines ingest from Cloud Storage (S3/GCS) and write directly to a hosted vector store (e.g. Pinecone/Qdrant/pgvector).

### 2. Hot-Swappable Prompts vs. Redeployment Overhead
* **The Pitfall:** Storing prompts purely in Python scripts, meaning a minor text tweak requires a full Docker rebuild and CI/CD deploy.
* **Mitigation:** `app/prompts/registry.py` provides a standardized interface that fallbacks from local templates to a remote config server (e.g. Langfuse Prompt Hub, database cache, or environment config), enabling hot-swapping prompts on the fly in production.

### 3. OpenTelemetry Observability vs. Local Trace Logging
* **The Pitfall:** Writing custom tracers that log to local files or local DBs, introducing massive database writes and latency.
* **Mitigation:** `observability/tracer.py` leverages OpenTelemetry standard API wrappers to cleanly export traces to distributed APM tools (such as Langfuse, Langsmith, or Datadog) while caching traces asynchronously.

### 4. Evaluation Scaling & Metrics
* **The Pitfall:** Hardcoding a static offline evaluator file that scales poorly.
* **Mitigation:** `evaluation/offline_eval.py` is written to hook directly into production evaluations (using tools like RAGAS or TruLens) and leverages remote data schemas, leaving the local `golden_dataset.json` purely as a small schema mock for developer checks.

---

## 🚀 Getting Started

### Prerequisites
* Docker & Docker Compose
* Python 3.11+
* Poetry (optional, for local development dependency management)

### Local Development Setup
1. Clone this repository.
2. Initialize virtual environment:
   ```bash
   poetry install
   ```
3. Set up environment variables:
   ```bash
   cp .env.example .env
   ```
4. Start the backend, frontend, and local services (Redis Cache) via Docker Compose:
   ```bash
   docker-compose up --build
   ```

### Running Services
* **Backend API:** `http://localhost:8000` (Swagger docs available at `/docs`)
* **Frontend Web Client:** `http://localhost:8501`
* **Local Cache Store (Redis):** `localhost:6379`
