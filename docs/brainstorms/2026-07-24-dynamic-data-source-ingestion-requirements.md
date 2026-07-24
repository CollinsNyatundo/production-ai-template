---
date: 2026-07-24
topic: dynamic-data-source-ingestion
origin: docs/ideation/2026-07-24-connectors-and-apis-rethink-ideation.md
---

# Requirements: Dynamic Data Source Ingestion & Live Vector Syncing

## Summary
Transform Nexus AI into a self-service knowledge base management workstation by introducing a **Dynamic Data Source Ingestion Drawer** in the Streamlit frontend and supporting backend APIs for real-time vector embedding and indexing of GitHub repositories, web URLs, local files, and SQL databases.

## Problem Frame
Currently, `app/services/rag_pipeline.py` supports vector indexing and retrieval, but the frontend lacks any user interface to trigger or monitor data ingestion. Users cannot upload custom documents, connect GitHub repositories, or sync web URLs without manual terminal scripts or database seeding.

## Actors & Key Flows

### Actors
- **A1: Developer / Data Admin**: Wants to connect repositories, URLs, or files and monitor embedding job progress.
- **A2: Analyst / Chat User**: Wants chat answers grounded in newly ingested data sources with real-time vector context attribution.

### Key Flows
- **F1: Connect & Configure Data Source**: User opens the Data Source Ingestion Drawer from the sidebar, selects source type (GitHub Repo, Web URL, Local File/Folder, SQL Query), inputs source details, and triggers sync.
- **F2: Live Vector Embedding & Job Tracking**: Backend processes text, splits into semantic chunks, generates vector embeddings, and streams chunking/embedding progress (`0-100%`) to the UI.
- **F3: Knowledge Base Collection Management**: User views active collections list with chunk counts, vector dimensions, sync timestamps, and options to re-sync or delete collections.

---

## Key Decisions

- **Multi-Source Support**: Initial release supports 4 distinct connectors:
  1. 🌐 Web Page / Documentation URL scraper.
  2. 💻 GitHub Repository clone/fetch connector.
  3. 📁 Local File & Folder uploader (`.md`, `.pdf`, `.txt`, `.py`, `.json`, `.csv`).
  4. 🗄️ SQL Database query extractor (PostgreSQL / MySQL / BigQuery).
- **Tenant-Isolated Vector Namespaces**: Every ingested document batch is tagged with the active session's `tenant_id`, ensuring strict multi-tenant isolation in OpenKB / Pinecone / Qdrant.
- **Asynchronous Ingestion Job Status**: Long-running embedding jobs return a `job_id`, allowing the frontend to poll status (`GET /api/v1/ingest/status/{job_id}`) and display an interactive progress bar without blocking the Streamlit UI event loop.

---

## Requirements

### Frontend UI & Drawer Components
R1. The sidebar must feature a "📁 Data Sources & Ingestion" trigger button that opens a centered `@st.dialog` modal or sidecar drawer.
R2. The ingestion modal must provide a tabbed selector for source types: `🌐 Web URL`, `💻 GitHub Repo`, `📁 File Upload`, and `🗄️ SQL Database`.
R3. Triggering ingestion must render a live progress indicator (`st.progress`) with real-time status captions (e.g. `Fetching 12 files...`, `Chunking 84 paragraphs...`, `Generating embeddings 65%...`).
R4. The modal must display an "Active Knowledge Collections" table listing collection name, source type, chunk count, file size, vector model, and sync timestamp.
R5. Each active collection card must include a `🔄 Re-Sync` button and a `🗑️ Delete` button.

### Backend API & Vector Pipeline
R6. The FastAPI backend must expose endpoints:
- `POST /api/v1/ingest` (Accepts `source_type`, `uri_or_file`, `tenant_id`, `chunk_size`, `chunk_overlap`).
- `GET /api/v1/ingest/status/{job_id}` (Returns progress percentage, status enum `processing|completed|failed`, and error details).
- `GET /api/v1/collections?tenant_id={tenant_id}` (Returns metadata list of active collections).
- `DELETE /api/v1/collections/{collection_id}` (Purges vector embeddings and document chunks).
R7. Document chunking must use configurable recursive character text splitters with metadata preserving source file path, line numbers, and creation timestamp.
R8. Ingested vectors must be written to OpenKB / Pinecone / Qdrant with `tenant_id` namespace filters.

---

## Scope Boundaries

### Included in Version 1
- Streamlit Data Source Ingestion Drawer dialog with 4 connector tabs.
- Live progress bar polling via backend async job status endpoint.
- Knowledge Collection Manager table with Delete and Re-sync capabilities.
- Multi-tenant vector namespace tagging.

### Deferred for Later
- Automatic background cron scheduled web re-crawling.
- Direct OAuth integrations with Google Drive / Notion / Slack.

---

## Acceptance Examples

AE1. **Web URL Sync Test:**
- **Trigger:** User enters `https://docs.streamlit.io` in the Web URL tab and clicks "⚡ Start Ingestion".
- **Outcome:** Progress bar animates `0% -> 100%`; backend chunks and embeds 45 vector documents into OpenKB; new collection `streamlit-docs` appears under Active Collections table.

AE2. **Tenant Boundary Test:**
- **Trigger:** User uploads `financial_q3.pdf` under `tenant_id: tenant-alpha`.
- **Outcome:** Document is indexed under namespace `tenant-alpha`. A query executed under `tenant_id: tenant-beta` does NOT return chunks from `financial_q3.pdf`.
