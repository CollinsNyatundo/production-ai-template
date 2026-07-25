---
date: 2026-07-24
topic: chat-frontend-redesign
origin: docs/brainstorms/2026-07-24-chat-frontend-redesign-requirements.md
status: active
---

# Technical Plan: Nexus AI Chat Frontend Experience Overhaul

## 1. Problem Frame & Origin
This plan establishes the technical implementation details for the chat frontend redesign specified in [docs/brainstorms/2026-07-24-chat-frontend-redesign-requirements.md](file:///d:/Projects/ai_template/docs/brainstorms/2026-07-24-chat-frontend-redesign-requirements.md). 

Currently, the single-column Streamlit chat layout forces excessive vertical scrolling when viewing long code blocks or architectural specs. Users must also manually navigate a 78-skill modal for every session and inspect context sources via truncated plain text without visual relevance scoring or export options.

## 2. Requirements Traceability

| Requirement ID | Description | Primary Implementation Unit |
|---|---|---|
| **R1** | Dual-column split layout (`st.columns([6, 6])`) when `canvas_open=True` | **U1** |
| **R2** | "📄 Open in Canvas" button on assistant code/spec blocks | **U1** |
| **R3** | Canvas sidecar panel with title, copy, download, and close controls | **U1** |
| **R4** | 4 quick-select Skill Preset chips (`🎛️ PM Discovery`, `🛠️ Code Audit`, etc.) | **U2** |
| **R5** | Instant session state skill pill update upon preset chip selection | **U2** |
| **R6** | Shortcut popover displaying `@` connectors and `/` execution modes | **U2** |
| **R7** | Visual vector context source cards with relevance percentage meters | **U3** |
| **R8** | "🔍 Inspect Full Chunk" button triggering un-truncated modal view | **U3** |
| **R9** | Per-message action bar (`🔄 Retry`, `🌿 Fork`, `📥 Export`, `📋 Copy`) | **U4** |
| **R10** | Session branching (`session-{timestamp}-fork`) on `🌿 Fork Session` | **U4** |
| **R11** | Downloadable Markdown report generation on `📥 Export Report` | **U4** |

---

## 3. High-Level Technical Design

```
+---------------------------------------------------------------------------------------+
|  Nexus AI Workspace — Streamlit Layout Router (frontend/app.py)                       |
+------------------------------------+--------------------------------------------------+
|  MAIN CHAT THREAD (6 or 12 Cols)   |  SIDECAR CANVAS PANE (6 Cols, Conditional)      |
|  - Hero & Command Input Card       |  - Title Header & Close Button (❌)             |
|  - Skill Preset Chips & Shortcuts  |  - Syntax-Highlighted Code / Spec Editor        |
|  - Assistant Messages + Action Bar |  - Copy to Clipboard & Download Actions          |
|  - Vector Cards + Chunk Inspector  |                                                  |
+------------------------------------+--------------------------------------------------+
```

---

## 4. Implementation Units

### Unit U1: Dynamic Sidecar Canvas Split Layout & State Manager
- **Goal**: Enable a dual-column split view (`st.columns([6, 6])`) when viewing code/specs in Canvas mode, with interactive copy, download, and close controls.
- **Files**:
  - `frontend/components/canvas_sidecar.py` [NEW]
  - `frontend/app.py` [MODIFY]
  - `frontend/styles/theme.css` [MODIFY]
- **Key Decisions**:
  - Use `st.session_state.canvas_open` (bool) and `st.session_state.active_canvas_artifact` (dict: `{title, content, language, filename}`).
  - When `canvas_open` is True, `app.py` splits the main workspace into `col_left, col_right = st.columns([6, 6])`.
  - Render "📄 Open in Canvas" buttons next to code blocks in assistant chat messages.
- **Verification Scenarios**:
  - `AE1`: Click "📄 Open in Canvas" on an assistant code block -> Layout switches to `[6, 6]` split view, canvas sidecar opens with code content, copy/download controls work, and clicking "❌" restores single-column layout.

---

### Unit U2: Quick-Select Skill Presets & Command Palette Shortcuts
- **Goal**: Add 1-click Skill Preset Chips on the prompt toolbar and a popover helper for `@` connectors and `/` execution modes.
- **Files**:
  - `frontend/components/chat_card.py` [MODIFY]
  - `frontend/styles/theme.css` [MODIFY]
- **Key Decisions**:
  - Define 4 preset skill maps:
    - `🎛️ PM Discovery`: `["interview-script", "customer-journey-map", "opportunity-solution-tree"]`
    - `🛠️ Code Audit`: `["ce-simplify-code", "systematic-debugging", "test-driven-development"]`
    - `🚀 GTM Launch`: `["gtm-strategy", "ideal-customer-profile", "positioning-ideas"]`
    - `📄 PRD & Spec`: `["create-prd", "user-stories", "test-scenarios"]`
  - Render preset buttons directly inside `chat_card.py` above the text area; clicking a preset updates `st.session_state.active_skills` and triggers `st.rerun()`.
  - Add a popover button `ℹ️ Shortcuts` on the toolbar displaying `@` connectors and `/` modes.
- **Verification Scenarios**:
  - `AE2`: Click `🛠️ Code Audit` preset chip -> `st.session_state.active_skills` updates to `["ce-simplify-code", "systematic-debugging", "test-driven-development"]`, displaying active skill pill badges above prompt textarea.

---

### Unit U3: Visual Vector Retrieval Context Source Cards & Dialog Inspector
- **Goal**: Transform plain text context sources into enterprise cards with color-coded relevance meters (`85%+` green, `60-84%` amber) and modal chunk inspection.
- **Files**:
  - `frontend/components/trajectory_view.py` [MODIFY]
  - `frontend/components/modals.py` [MODIFY]
  - `frontend/styles/theme.css` [MODIFY]
- **Key Decisions**:
  - Compute relevance score percentage `score_pct = int(score * 100)`.
  - Display progress bar / badge (`89% Relevance`).
  - Render "🔍 Inspect Full Chunk" button triggering `@st.dialog("📄 Vector Chunk Inspection")` showing un-truncated text and metadata dictionary.
- **Verification Scenarios**:
  - `AE3`: Context sources returned from backend render with colored relevance score meters, source type badges (`OpenKB Vector`, `Web Search`, `Code Search`), and clicking "🔍 Inspect Full Chunk" opens an un-truncated modal dialog.

---

### Unit U4: Per-Message Turn Actions (Fork Session, Retry, Export Markdown Report)
- **Goal**: Add turn-level action buttons below assistant responses for conversation branching, report downloading, and payload copying.
- **Files**:
  - `frontend/components/trajectory_view.py` [MODIFY]
  - `frontend/components/sidebar.py` [MODIFY]
  - `frontend/app.py` [MODIFY]
- **Key Decisions**:
  - Render action bar under assistant responses:
    - `🔄 Retry`: Sets `st.session_state.retry_prompt = user_query` and triggers re-execution.
    - `🌿 Fork Session`: Creates new `st.session_state.session_id = f"session-{int(time.time())}-fork"` copying messages up to current turn index.
    - `📥 Export Report`: Uses `st.download_button` with Markdown string containing prompt, answer, sources, and trajectory.
    - `📋 Copy Payload`: Prepares raw JSON payload download/copy.
- **Verification Scenarios**:
  - `AE4`: Click `🌿 Fork Session` on Turn 2 of a 4-turn thread -> active `session_id` updates to `session-<timestamp>-fork` carrying turns 1-2 into new session state. Click `📥 Export Report` -> downloads valid Markdown report file.

---

## 5. System-Wide Impact & Dependencies

- **Dependencies**: Streamlit layout components, `httpx`, `theme.css`.
- **Breaking Changes**: None. All existing backend endpoints (`/api/query`, `/api/session/{id}`) and session state keys remain fully compatible.
- **Docker Rebuild**: Required after updating `frontend/` files via `docker compose up --build -d`.

---

## 6. Verification Plan

1. **Docker Container Build**:
   - Run `docker compose up --build -d` to compile fresh images.
   - Verify health: `powershell -Command "Invoke-RestMethod -Uri http://localhost:8501/_stcore/health"` (Expect `ok`).
2. **Visual & UI Testing (`browser_subagent`)**:
   - Verify Canvas Sidecar split view on code blocks.
   - Verify Skill Preset chips and active skill pills.
   - Verify Context Source Cards with relevance score meters and chunk dialog inspector.
   - Verify Message Action bar (Retry, Fork, Export Markdown).
