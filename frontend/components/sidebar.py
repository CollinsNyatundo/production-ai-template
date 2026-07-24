import os
import time

import httpx
import streamlit as st

from components.modals import (
    open_artifacts_modal,
    open_health_modal,
    open_ingestion_modal,
    open_skills_modal,
    open_tenants_modal,
)


def render_sidebar(backend_api_url: str, default_api_key: str):
    with st.sidebar:
        st.markdown("### ✳️ Nexus AI")

        # + New Chat Button
        if st.button("➕ New", use_container_width=True, type="primary"):
            st.session_state.messages = []
            st.session_state.session_id = f"session-{int(time.time())}"
            st.rerun()

        st.markdown("---")

        # Navigation Links
        st.markdown("**Navigation**")
        if st.button("💻 Computer", use_container_width=True):
            open_health_modal()
        if st.button("📁 Spaces", use_container_width=True):
            open_tenants_modal()
        if st.button("📥 Data Sources", use_container_width=True):
            open_ingestion_modal(backend_api_url)
        if st.button("📄 Artifacts", use_container_width=True):
            open_artifacts_modal()

        st.markdown("---")

        # Customize Section & Skills
        st.markdown("**⚙️ Customize**")
        num_skills = len(st.session_state.active_skills)
        skill_badge = f"({num_skills})" if num_skills > 0 else ""
        if st.button(f"⚡ Skills {skill_badge}", use_container_width=True):
            open_skills_modal()

        # Memory & Cache Settings
        with st.expander("💾 Memory & Cache"):
            use_cache = st.checkbox("Enable Semantic Cache", value=True)
            st.markdown("---")
            st.markdown("**🧠 Persistent Memory (Mem0)**")
            if st.button("Inspect Active Memories", use_container_width=True, key="btn_inspect_mem0"):
                try:
                    headers = {"X-API-Key": os.getenv("FRONTEND_API_KEY", "")}
                    with httpx.Client() as client:
                        resp = client.get(
                            f"{backend_api_url}/api/memory",
                            headers=headers,
                            timeout=5.0,
                        )
                    if resp.status_code == 200:
                        mems = resp.json().get("memories", [])
                        if mems:
                            for m in mems:
                                st.caption(f"• {m.get('text')} (`{m.get('memory_id')}`)")
                        else:
                            st.caption("No persistent memories stored yet.")
                except Exception as ex:
                    st.caption(f"Memory offline: {ex}")

            st.markdown("---")
            if st.button("Clear Session History", use_container_width=True):
                try:
                    headers = {"X-API-Key": os.getenv("FRONTEND_API_KEY", "")}
                    with httpx.Client() as client:
                        resp = client.delete(
                            f"{backend_api_url}/api/session/{st.session_state.session_id}",
                            headers=headers,
                            timeout=5.0,
                        )
                    if resp.status_code == 200:
                        st.session_state.messages = []
                        st.success("Session history cleared.")
                    else:
                        st.error(f"Failed to clear session ({resp.status_code})")
                except Exception as ex:
                    st.error(f"Backend offline: {ex}")

        with st.expander("🔌 Connectors & API"):
            st.text_input("Backend URL", value=backend_api_url, disabled=True)
            api_key_input = st.text_input(
                "API Key",
                value=default_api_key,
                type="password",
                help="Sent as X-API-Key with every backend request.",
            )

        st.markdown("---")

        # Session History
        st.markdown("**🕒 History**")
        st.session_state.session_id = st.text_input("Session ID", value=st.session_state.session_id)

        st.markdown("---")

        # Bottom Sidebar Footer
        if st.button("🚀 Upgrade plan", use_container_width=True):
            st.toast("Pro plan upgrade available.")

        st.caption("👤 **magna01** (Free plan)")
        if api_key_input:
            st.markdown("<span style='color:#4ADE80;'>🔑 Authenticated</span>", unsafe_allow_html=True)
        else:
            st.markdown("<span style='color:#FBBF24;'>⚠️ Dev Mode</span>", unsafe_allow_html=True)

        return use_cache, api_key_input
