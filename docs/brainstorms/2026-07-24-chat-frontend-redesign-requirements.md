---
date: 2026-07-24
topic: chat-frontend-redesign
---

# Requirements: Nexus AI Chat Frontend Experience Overhaul

## Summary
Transform the Nexus AI Streamlit frontend into a dual-pane developer workstation featuring an interactive sidecar canvas, quick-select skill preset packs, rich vector retrieval context cards, and per-message turn management actions.

## Problem Frame
The current single-column vertical chat layout forces heavy scrolling when viewing code blocks, data tables, or architectural specs. Users must also manually navigate a 78-skill modal for every session and inspect context sources via plain text truncation without visual relevance scoring or export capabilities.

## Key Decisions

- **Dual-Pane Sidecar Canvas Split View**: The chat interface dynamically resizes between a single full-width column (`st.columns([12])`) and a split dual-pane layout (`st.columns([6, 6])` or `[7, 5]`) whenever an artifact (code, spec, PRD) is opened in Canvas mode.
- **Skill Preset Chips & Quick Toolbar Controls**: Skill selections are streamlined into 4 toolbar preset chips (PM Discovery, Code Audit, GTM Launch, PRD & Spec) alongside a shortcut help trigger for `@` connectors and `/` execution modes.
- **Visual Vector Debugging Context Cards**: Retrieval context sources feature color-coded relevance meters, OpenKB/Web/Code source badges, and full chunk dialog inspection.
- **Per-Message Action Toolbar**: Every assistant response carries turn-level utilities: Retry with Skill, Fork Session, Export Markdown Report, and Copy Trajectory JSON.

## Requirements

### Canvas & Layout Architecture
R1. The workspace layout must support dual-column split state (`canvas_open=True`) and single-column thread state (`canvas_open=False`) controlled by session state.
R2. Code blocks, PRDs, and markdown specs in assistant responses must include an "📄 Open in Canvas" button that populates the active canvas state and opens the sidecar editor.
R3. The Canvas sidecar editor must display artifact title, file type badge, copy button, download button, syntax highlighting, and a close toggle ("❌").

### Prompt Command Deck & Skill Presets
R4. The prompt toolbar must display 4 quick-select Skill Preset chips (`🎛️ PM Discovery`, `🛠️ Code Audit`, `🚀 GTM Launch`, `📄 PRD & Spec`).
R5. Clicking a Skill Preset chip must instantly update `st.session_state.active_skills` with pre-defined skill lists and render skill pill tags.
R6. A shortcut help trigger on the prompt toolbar must list available `@` connectors (`OpenKB Vector`, `Web Search`, `Code Search`) and `/` execution modes (`/research`, `/council`, `/learn`).

### Context Inspection & Vector Cards
R7. Context sources drawers must render styled cards featuring relevance percentage meters (`85%+` green, `60-84%` amber), source badges, and snippet preview boxes.
R8. Each context source card must include a "🔍 Inspect Full Chunk" button triggering an un-truncated modal view of the chunk text and vector metadata.

### Message Turn Management & Exports
R9. Every assistant response card must carry a bottom action bar with `🔄 Retry`, `🌿 Fork Session`, `📥 Export Report`, and `📋 Copy Payload`.
R10. Clicking `🌿 Fork Session` must branch the conversation into a new session ID (`session-{timestamp}-fork`) carrying history up to that turn.
R11. Clicking `📥 Export Report` must generate a downloadable Markdown report containing prompt, response, context sources, and execution trajectory.

## Scope Boundaries

### Included in Version 1
- Canvas sidecar panel inside Streamlit layout.
- Skill preset chips and toolbar shortcut popover.
- Visual relevance meters and chunk dialog inspector.
- Message action bar (Retry, Fork, Export, Copy).

### Deferred for Later
- Live SSE real-time streaming progress steps (requires FastAPI streaming endpoint modifications).
- Native custom JavaScript keypress interception inside standard Streamlit text inputs.

## Acceptance Examples

AE1. **Canvas Open Test:**
- **Trigger:** User clicks "📄 Open in Canvas" on a code block.
- **Outcome:** Layout switches to split view (`st.columns([6, 6])`); code block renders inside right-hand canvas editor with copy/download controls.

AE2. **Skill Preset Toggle Test:**
- **Trigger:** User clicks `🛠️ Code Audit` preset chip.
- **Outcome:** `st.session_state.active_skills` updates to `["ce-simplify-code", "systematic-debugging", "test-driven-development"]` and skill pills appear above prompt textarea.

AE3. **Session Fork Test:**
- **Trigger:** User clicks `🌿 Fork Session` on Turn 2 of a 4-turn thread.
- **Outcome:** Active `session_id` changes to `session-<timestamp>-fork`, carrying turns 1-2 into the new session state.
