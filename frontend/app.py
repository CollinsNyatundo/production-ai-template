import os
import sys
from pathlib import Path

import httpx
import streamlit as st

_FRONTEND_DIR = Path(__file__).resolve().parent
if str(_FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(_FRONTEND_DIR))

from components.canvas_sidecar import render_canvas_sidecar  # noqa: E402
from components.chat_card import render_chat_card  # noqa: E402
from components.sidebar import render_sidebar  # noqa: E402
from components.trajectory_view import (  # noqa: E402
    render_message_action_bar,
    render_sources,
    render_trajectory,
)
from skills import ALL_SKILLS  # noqa: E402

# 1. Page Configuration
st.set_page_config(
    page_title="Nexus AI — Enterprise Workspace",
    page_icon="✳️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. Inject External Design System Theme CSS
theme_css_path = _FRONTEND_DIR / "styles" / "theme.css"
if theme_css_path.exists():
    with open(theme_css_path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def resolve_backend_url(raw_url: str) -> str:
    if "http://app:8000" in raw_url:
        try:
            with httpx.Client(timeout=1.0) as client:
                r = client.get(f"{raw_url}/health")
                if r.status_code == 200:
                    return raw_url
        except Exception:
            return "http://localhost:8000"
    return raw_url


# 3. Environment & Configuration
RAW_BACKEND_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000")
BACKEND_API_URL = resolve_backend_url(RAW_BACKEND_URL)
DEFAULT_API_KEY = os.getenv("FRONTEND_API_KEY", "")

# 4. Session State Initialization
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = "prod-session-001"
if "tenant_id" not in st.session_state:
    st.session_state.tenant_id = "tenant-prod-01"
if "active_skills" not in st.session_state:
    st.session_state.active_skills = []
if "selected_model" not in st.session_state:
    st.session_state.selected_model = "meta/llama-3.3-70b-instruct"
if "search_mode" not in st.session_state:
    st.session_state.search_mode = "🔍 Search (Auto Agent)"
if "code_search_active" not in st.session_state:
    st.session_state.code_search_active = False
if "canvas_open" not in st.session_state:
    st.session_state.canvas_open = False


def get_headers(api_key_str: str) -> dict:
    return {"X-API-Key": api_key_str} if api_key_str else {}


# 5. Render Sidebar Navigation & Settings
use_cache, api_key_input = render_sidebar(BACKEND_API_URL, DEFAULT_API_KEY)

# 6. Main Workspace Layout Routing (Single Column vs Dual Column Split)
canvas_is_open = st.session_state.canvas_open

if canvas_is_open:
    main_col, canvas_col = st.columns([6, 6])
else:
    main_col = st.container()
    canvas_col = None

# Render Canvas Sidecar in Right Column if Open
if canvas_is_open and canvas_col is not None:
    with canvas_col:
        render_canvas_sidecar()

# Render Main Workspace Area in Left/Main Column
with main_col:
    # Header Row
    top_col1, top_col2 = st.columns([8, 2])
    with top_col1:
        st.markdown(
            "<span style='background-color:#1D1F27; padding:4px 12px; border-radius:16px; font-size:0.8rem;"
            " color:#9CA3AF; border: 1px solid #2A2C38;'>Free plan · Upgrade</span>",
            unsafe_allow_html=True,
        )
    with top_col2:
        st.markdown("<div style='text-align:right; color:#9CA3AF;'>⚙️ Workspace</div>", unsafe_allow_html=True)

    # Render Unified Prompt Card
    user_prompt_text, search_mode_choice, selected_model_choice, submit_query_clicked = render_chat_card()

    # Render Existing Chat Message Thread & Trajectories
    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                render_sources(msg.get("sources", []), msg_idx=idx)
                render_trajectory(msg.get("trajectory", []))
                render_message_action_bar(msg, msg_idx=idx)

    # Handle New Query Execution
    if submit_query_clicked and user_prompt_text.strip():
        user_query = user_prompt_text.strip()
        st.session_state.messages.append({"role": "user", "content": user_query})

        with st.chat_message("user"):
            st.markdown(user_query)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing prompt and synthesizing context..."):
                try:
                    headers = get_headers(api_key_input)
                    skill_prompts = [ALL_SKILLS[s]["prompt"] for s in st.session_state.active_skills if s in ALL_SKILLS]

                    query_payload = {
                        "query": user_query,
                        "session_id": st.session_state.session_id,
                        "use_cache": use_cache,
                        "model": selected_model_choice,
                        "search_mode": search_mode_choice,
                    }

                    if skill_prompts:
                        combined_guidance = "\n".join(skill_prompts)
                        query_payload["query"] = f"[System Skill Guidance: {combined_guidance}]\n\n{user_query}"

                    with httpx.Client() as client:
                        resp = client.post(
                            f"{BACKEND_API_URL}/api/query",
                            headers=headers,
                            json=query_payload,
                            timeout=120.0,
                        )

                    if resp.status_code == 200:
                        data = resp.json()
                        answer = data.get("answer", "No answer provided.")
                        sources = data.get("sources", [])
                        trajectory = data.get("trajectory", [])

                        st.markdown(answer)
                        new_msg_idx = len(st.session_state.messages)
                        render_sources(sources, msg_idx=new_msg_idx)
                        render_trajectory(trajectory)

                        new_assistant_msg = {
                            "role": "assistant",
                            "content": answer,
                            "sources": sources,
                            "trajectory": trajectory,
                        }
                        st.session_state.messages.append(new_assistant_msg)
                        render_message_action_bar(new_assistant_msg, msg_idx=new_msg_idx)

                    elif resp.status_code == 401:
                        st.error("401 Unauthorized — Please check your API Key in the sidebar connectors.")
                    else:
                        st.error(f"Error {resp.status_code}: {resp.text}")

                except Exception as e:
                    st.error(f"Failed to connect to backend at {BACKEND_API_URL}: {e}")
