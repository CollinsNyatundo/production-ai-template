---
date: 2026-07-24
topic: dynamic-data-source-ingestion
origin: docs/brainstorms/2026-07-24-dynamic-data-source-ingestion-requirements.md
status: active
---

# Technical Plan: Dynamic Data Source Ingestion & Live Vector Syncing

## 1. Problem Frame & Origin
This technical plan establishes the implementation breakdown for the **Dynamic Data Source Ingestion Drawer** defined in [docs/brainstorms/2026-07-24-dynamic-data-source-ingestion-requirements.md](file:///d:/Projects/ai_template/docs/brainstorms/2026-07-24-dynamic-data-source-ingestion-requirements.md).

Currently, `app/services/rag_pipeline.py` supports vector searching, but there are no backend API endpoints or frontend UI controls to ingest new documents, connect web URLs/GitHub repos, or monitor embedding progress.

## 2. Requirements Traceability

| Requirement ID | Description | Implementation Unit |
|---|---|---|
| **R1** | Sidebar "📁 Data Sources & Ingestion" trigger button | **U3** |
| **R2** | Tabbed ingestion modal (`🌐 Web`, `💻 GitHub`, `📁 File`, `🗄️ SQL`) | **U3** |
| **R3** | Live progress bar (`st.progress`) polling `0-100%` job status | **U3** |
| **R4** | Active Knowledge Collections table with metadata cards | **U3** |
| **R5** | Collection `🔄 Re-Sync` and `🗑️ Delete` actions | **U3** |
| **R6** | FastAPI endpoints (`POST /api/v1/ingest`, `GET /status`, `DELETE /collections`) | **U1** |
| **R7** | Recursive character chunking & path/metadata preservation | **U2** |
| **R8** | Multi-tenant namespace isolation (`tenant_id` tagging) | **U1** |

---

## 3. High-Level Technical Design

```
+-----------------------------------------------------------------------------------+
| STREAMLIT FRONTEND (frontend/components/modals.py)                                |
| - Open Modal: @st.dialog("📁 Data Sources & Live Ingestion")                      |
| - Tabs: [Web URL] [GitHub Repo] [File Upload] [SQL Query]                        |
| - Polls backend: GET /api/v1/ingest/status/{job_id} -> renders st.progress        |
+-----------------------------------------------------------------------------------+
                                      | POST /api/v1/ingest
                                      v
+-----------------------------------------------------------------------------------+
| FASTAPI BACKEND CORE (app/api/ingest.py & app/services/ingestion_service.py)       |
| - Job Queue Engine: Assigns job_id, runs background asyncio task                  |
| - Multi-Source Extractors (Web, GitHub, File, SQL)                                |
| - Chunking & Vector Embedding (app/services/rag_pipeline.py)                      |
| - Namespace Tagging: tenant_id -> OpenKB Vector Store                             |
+-----------------------------------------------------------------------------------+
```

---

## 4. Implementation Units

### Unit U1: Ingestion Service & FastAPI API Endpoints
- **Goal**: Create backend ingestion service and expose FastAPI REST endpoints.
- **Files**:
  - `app/services/ingestion_service.py` [NEW]
  - `app/api/ingest.py` [NEW]
  - `app/main.py` [MODIFY]
- **Key Decisions**:
  - Maintain job status dictionary in `ingestion_service.py`: `{job_id: {status: "processing|completed|failed", progress: 0.85, chunks: 42, error: None}}`.
  - Expose `/api/v1/ingest`, `/api/v1/ingest/status/{job_id}`, `/api/v1/collections`, and `/api/v1/collections/{id}`.
- **Verification Scenarios**:
  - `AE1`: `POST /api/v1/ingest` with `source_type="web"`, `url="https://example.com"` returns `{"job_id": "job-123", "status": "processing"}`. Subsequent polling to `/status/job-123` returns `1.0` progress and status `"completed"`.

---

### Unit U2: Multi-Source Text Extractors
- **Goal**: Build modular connectors for extracting text from web URLs, local files, and GitHub repos.
- **Files**:
  - `app/services/connectors/__init__.py` [NEW]
  - `app/services/connectors/web_scraper.py` [NEW]
  - `app/services/connectors/file_extractor.py` [NEW]
- **Key Decisions**:
  - `web_scraper.py`: Fetches HTML via `httpx` and extracts readable text paragraphs using `html.parser` / BeautifulSoup.
  - `file_extractor.py`: Handles plain text, Markdown, Python, JSON, and CSV uploads.
- **Verification Scenarios**:
  - `AE2`: Passing a raw URL or text file produces structured document chunks carrying metadata (`source`, `category`, `tenant_id`, `timestamp`).

---

### Unit U3: Streamlit Data Sources Ingestion Modal & Collections Manager
- **Goal**: Add a Data Sources trigger in the sidebar and a tabbed `@st.dialog` modal with live progress polling and collection management.
- **Files**:
  - `frontend/components/modals.py` [MODIFY]
  - `frontend/components/sidebar.py` [MODIFY]
- **Key Decisions**:
  - Add `open_ingestion_modal()` dialog with 4 tabs: `🌐 Web URL`, `💻 GitHub Repo`, `📁 File Upload`, `🗄️ SQL Database`.
  - Add "Active Knowledge Collections" list displaying collection name, source, chunk count, and `🗑️ Delete` button.
- **Verification Scenarios**:
  - `AE3`: Click `📁 Data Sources` in sidebar -> Modal opens -> Select `🌐 Web URL` tab -> Submit `https://docs.streamlit.io` -> Live progress bar animates to 100% and collection appears under Active Collections table.

---

## 5. System-Wide Impact & Verification

1. **Docker Container Build**: Rebuild `ai_template-app-1` and `ai_template-frontend-1` via `docker compose up --build -d`.
2. **Backend API Test**: Verify `/api/v1/collections` returns 200 OK.
3. **Frontend UI Test**: Use `browser_subagent` to test opening the Data Sources modal and submitting a Web URL ingestion job.
