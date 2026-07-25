import json
import time

import streamlit as st

from components.modals import open_chunk_inspector_modal


def render_sources(sources: list, msg_idx: int = 0):
    if not sources:
        return
    with st.expander(f"🔍 Context Sources ({len(sources)})"):
        for s_idx, src in enumerate(sources):
            meta = src.get("metadata", {})
            source_name = meta.get("source", "Knowledge Base")
            score = src.get("score", 0.85)
            score_pct = int(score * 100)

            if "openkb" in str(source_name).lower() or meta.get("category") == "retrieval":
                badge_html = "<span class='badge-openkb'>🧠 OpenKB Vector</span>"
            elif "web" in str(source_name).lower():
                badge_html = "<span class='badge-web'>🌐 Web Search</span>"
            else:
                badge_html = "<span class='badge-code'>💻 Code Search</span>"

            # Source Card Layout
            card_col1, card_col2 = st.columns([7, 3])
            with card_col1:
                st.markdown(
                    f"{badge_html} <b>{source_name}</b> (Relevance: <b>{score_pct}%</b>)",
                    unsafe_allow_html=True,
                )
                st.progress(max(0.0, min(1.0, float(score))))
            with card_col2:
                if st.button("🔍 Inspect Chunk", key=f"btn_inspect_{msg_idx}_{s_idx}", use_container_width=True):
                    open_chunk_inspector_modal(src)

            st.text(src.get("content", "")[:300] + "...")
            st.markdown("---")


def render_trajectory(trajectory: list):
    if not trajectory:
        return
    with st.expander(f"🧠 Agent Execution Trajectory ({len(trajectory)} turns)"):
        for step in trajectory:
            turn = step.get("turn", 1)
            thought = step.get("thought", "")
            tool = step.get("tool", "none")
            obs = step.get("observation", "")

            st.markdown(
                f"<div class='trajectory-turn'>"
                f"<b>Turn {turn}</b> | Tool: <code>{tool}</code><br/>"
                f"<i>Thought:</i> {thought}<br/>"
                f"{f'<i>Obs:</i> {obs[:150]}...' if obs else ''}"
                f"</div>",
                unsafe_allow_html=True,
            )


def render_message_action_bar(msg: dict, msg_idx: int):
    if msg.get("role") != "assistant":
        return

    content = msg.get("content", "")
    sources = msg.get("sources", [])
    trajectory = msg.get("trajectory", [])

    st.markdown("<br/>", unsafe_allow_html=True)
    act_col1, act_col2, act_col3, act_col4, act_col5 = st.columns([2.5, 2.0, 2.5, 2.5, 2.5])

    # 1. Open in Canvas Button (if code block or long content present)
    with act_col1:
        if "```" in content or len(content) > 500:
            if st.button("📄 Open in Canvas", key=f"btn_canvas_{msg_idx}", use_container_width=True):
                # Detect language
                lang = "markdown"
                if "```python" in content:
                    lang = "python"
                elif "```json" in content:
                    lang = "json"
                elif "```bash" in content or "```sh" in content:
                    lang = "bash"

                st.session_state.active_canvas_artifact = {
                    "title": f"Turn {msg_idx + 1} Output",
                    "content": content,
                    "language": lang,
                    "filename": f"output_turn_{msg_idx + 1}.txt",
                }
                st.session_state.canvas_open = True
                st.rerun()

    # 2. Retry Button
    with act_col2:
        if st.button("🔄 Retry", key=f"btn_retry_{msg_idx}", use_container_width=True):
            # Find preceding user query
            user_q = ""
            for prev in reversed(st.session_state.messages[:msg_idx]):
                if prev.get("role") == "user":
                    user_q = prev.get("content", "")
                    break
            if user_q:
                st.session_state.retry_prompt = user_q
                st.toast("Copied prompt for retry!")
                st.rerun()

    # 3. Fork Session Button
    with act_col3:
        if st.button("🌿 Fork Session", key=f"btn_fork_{msg_idx}", use_container_width=True):
            new_session = f"session-{int(time.time())}-fork"
            st.session_state.session_id = new_session
            st.session_state.messages = list(st.session_state.messages[: msg_idx + 1])
            st.success(f"Branched into new session: `{new_session}`")
            st.rerun()

    # 4. Export Markdown Report Button
    with act_col4:
        report_md = f"# Nexus AI Execution Report\n\nSession: `{st.session_state.session_id}`\n\n"
        report_md += f"## Assistant Answer\n\n{content}\n\n"
        if sources:
            report_md += f"## Context Sources ({len(sources)})\n"
            for src in sources:
                report_md += f"- **{src.get('metadata', {}).get('source', 'KB')}**: {src.get('content', '')[:200]}...\n"
        st.download_button(
            label="📥 Export Report",
            data=report_md,
            file_name=f"nexus_report_{st.session_state.session_id}_{msg_idx}.md",
            mime="text/markdown",
            key=f"btn_export_{msg_idx}",
            use_container_width=True,
        )

    # 5. Copy Payload Button
    with act_col5:
        if st.button("📋 Copy JSON", key=f"btn_copy_json_{msg_idx}", use_container_width=True):
            payload_json = json.dumps({"content": content, "sources": sources, "trajectory": trajectory}, indent=2)
            st.session_state.active_canvas_artifact = {
                "title": f"Turn {msg_idx + 1} Raw JSON Payload",
                "content": payload_json,
                "language": "json",
                "filename": f"payload_turn_{msg_idx + 1}.json",
            }
            st.session_state.canvas_open = True
            st.toast("Opened raw payload in Canvas!")
            st.rerun()
