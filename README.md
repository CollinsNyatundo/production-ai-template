# Production-Ready AI Application Template

This repository represents a robust, enterprise-grade template for building scalable, secure, and observable AI/LLM-based applications. It is based on a modern **9-layer AI application architecture** and integrates the formal **Agent Harness** framework:

$$\mathcal{H} = (E, T, C, S, L, V)$$

It addresses and resolves the critical architectural pitfalls of typical prototypes (e.g. Git database bloat, volatile memory loss, hardcoded prompts, and token window crashes).

---

## 🏗️ 9-Layer Architecture Overview

The codebase is organized into modular layers that cleanly isolate concerns:

```
production-ai-template/
├── .claude/                  # Layer 9: AI Coding Agent Rules & Context
│   └── rules/                
│       ├── code-style.md     
│       └── testing.md        
├── app/                      
│   ├── components/           # Layer 2: Custom Retrieval (Hybrid search, Rerankers)
│   │   ├── hybrid_retriever.py
│   │   └── reranker.py
│   ├── services/             # Layer 3: Core Orchestration (Pipelines, Caches, Memory)
│   │   ├── rag_pipeline.py   # Main pipeline orchestrator
│   │   ├── semantic_cache.py # Redis/memory semantic caching
│   │   ├── conversation.py   # Persistent conversation registry
│   │   ├── context_manager.py# Layer 4 (C): Context Token Budget Manager
│   │   ├── hooks.py          # Layer 5 (L): Lifecycle Hooks Event Registry
│   │   ├── state_store.py    # Layer 4 (S): Persistent SQLite DB store
│   │   ├── query_rewriter.py 
│   │   └── query_router.py   
│   ├── prompts/              # Layer 4 (C): Prompt Templates & Registers
│   │   ├── templates.py      
│   │   └── registry.py       # Supports hot-swappable remote fetching
│   ├── agents/               # Layer 6 (E): Agentic Intelligence Layer
│   │   ├── executor.py       # (E) ReAct Agent Loop Coordinator
│   │   ├── document_grader.py
│   │   ├── query_decomposer.py
│   │   ├── adaptive_router.py
│   │   └── tools/            # Layer 2 (T): Tool Registry & Definitions
│   │       ├── registry.py   # (T) Centralized validation & schemas registrar
│   │       ├── vector_search.py
│   │       ├── web_search.py
│   │       └── code_search.py
│   ├── security/             # Layer 7: Guardrails (Input, Content, Output Filters)
│   │   ├── input_guard.py    
│   │   ├── content_filter.py 
│   │   └── output_filter.py  
│   ├── main.py               # Layer 1: Core API Entrypoint (FastAPI)
│   ├── config.py             
│   ├── models.py             
│   └── Dockerfile            
├── evaluation/               # Layer 8: Evaluation Framework
│   ├── golden_dataset.json   
│   ├── offline_eval.py       
│   └── trajectory_logger.py  # Layer 8 (V): Canonical JSONL trace exporter
├── observability/            # Layer 8: Observability Stack
│   ├── tracer.py             # OpenTelemetry standard span wrapper
│   ├── feedback.py           # Links user scores to spans
│   └── cost_tracker.py       # Tracks prompt/completion token pricing
├── data/                     # Ingestion configs (Raw files are git-ignored)
├── scripts/                  # DB migrations, seeding, healthchecks
├── frontend/                 # Separately containerized Streamlit client
└── tests/                    # CI-Ready unit & integration tests
```

---

## 🔬 Agent Harness Architecture: $\mathcal{H} = (E, T, C, S, L, V)$

This template fully implements the six harness components defined in state-of-the-art LLM engineering frameworks:

### 1. E (Execution Loop)
* **File:** `app/agents/executor.py`
* **Purpose:** Implements a ReAct-style agent control loop that cycles through thinking, action execution, and observation checks.
* **Mitigations:** Enforces a configurable `max_turns` limit (default: 5) to prevent runaway infinite tool-calling loops and handles exceptions gracefully by feeding error traces back into the reasoning context.

### 2. T (Tool Registry)
* **File:** `app/agents/tools/registry.py`
* **Purpose:** A centralized registrar for tools.
* **Mitigations:** 
  * Automatically generates JSON parameter schemas using Python signature introspection (`inspect`).
  * Enforces role-based permission checks (e.g. `code_search` requires `high` permission, whereas `vector_search` requires `low`). If permissions fail, the executor dynamically aborts the action.

### 3. C (Context Manager)
* **File:** `app/services/context_manager.py`
* **Purpose:** Manages the LLM's context window.
* **Mitigations:** Computes exact token lengths using `tiktoken` byte-pair encoding. When retrieved contexts exceed the model's budget (default: 1500 tokens), it dynamically prunes and truncates the lowest-scoring documents instead of overflowing the window.

### 4. S (State Store)
* **File:** `app/services/state_store.py`
* **Purpose:** A persistent relational database backing conversation memory.
* **Mitigations:** Uses SQLite (`app.db`) to record conversation sessions and state checkpoints. Snapshot variables are written to the DB after every agent execution step, enabling recovery from system crashes without losing the agent's path.

#### Database Schema:
```
+---------------------------------------+
|         conversation_history          |
+---------------------------------------+
| id          | INTEGER (PK)            |
| session_id  | TEXT                    |
| role        | TEXT                    |
| content     | TEXT                    |
| timestamp   | DATETIME                |
+---------------------------------------+

+---------------------------------------+
|           agent_checkpoints           |
+---------------------------------------+
| session_id  | TEXT (PK)               |
| current_step| INTEGER                 |
| state_json  | TEXT (JSON variables)   |
| trajectory  | TEXT (JSON steps list)  |
| updated_at  | DATETIME                |
+---------------------------------------+
```

### 5. L (Lifecycle Hooks)
* **File:** `app/services/hooks.py`
* **Purpose:** Pub/sub event emitter.
* **Mitigations:** Decouples core logic from observation utilities. Modules subscribe to events like `on_agent_start`, `on_tool_execute`, `on_llm_call`, and `on_error` to run middleware tasks concurrently using `asyncio.gather`.

### 6. V (Valuation Interface)
* **File:** `evaluation/trajectory_logger.py`
* **Purpose:** Benchmark valuation.
* **Mitigations:** Exports each agent execution run into a canonical JSONL file (`evaluation/eval_results/trajectory_runs.jsonl`), storing the query, steps, reasoning, and final generated output for offline benchmarking.

---

## 🚀 Getting Started

### Prerequisites
* Docker & Docker Compose
* Python 3.11+
* Poetry (optional, for local virtual environment management)

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
4. Start the backend API, Streamlit client, and Redis Cache:
   ```bash
   docker-compose up --build
   ```

### Running Tests
Execute the comprehensive test suite verifying the harness integration:
```bash
python -m pytest tests/
```

### API Usage Example
Request query execution with custom actor permissions via cURL:
```bash
curl -X POST "http://localhost:8000/api/query" \
     -H "Content-Type: application/json" \
     -d '{
       "query": "caching config",
       "session_id": "session-101",
       "use_cache": true,
       "actor_permission": "high"
     }'
```
