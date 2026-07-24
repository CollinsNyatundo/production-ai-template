import streamlit as st

from components.modals import open_skills_modal

# Preset Skill Combinations
SKILL_PRESETS = {
    "🎛️ PM Discovery": ["interview-script", "customer-journey-map", "opportunity-solution-tree"],
    "🛠️ Code Audit": ["ce-simplify-code", "systematic-debugging", "test-driven-development"],
    "🚀 GTM Launch": ["gtm-strategy", "ideal-customer-profile", "positioning-ideas"],
    "📄 PRD & Spec": ["create-prd", "user-stories", "test-scenarios"],
}


def render_hero():
    if not st.session_state.messages:
        st.markdown(
            """
            <div class="hero-container">
                <div class="hero-sub">Search & Intelligence</div>
                <div class="hero-title">What do you want to know?</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_chat_card():
    render_hero()

    with st.form(key="unified_single_chat_card", clear_on_submit=False):
        # Quick Skill Preset Chips Row
        preset_cols = st.columns([1, 1, 1, 1])
        for p_idx, (preset_name, skill_list) in enumerate(SKILL_PRESETS.items()):
            with preset_cols[p_idx]:
                if st.form_submit_button(preset_name, use_container_width=True):
                    st.session_state.active_skills = list(skill_list)
                    st.toast(f"Loaded preset: {preset_name}")
                    st.rerun()

        # Active Skill Pills (if loaded)
        if st.session_state.active_skills:
            skills_html = "".join([f"<span class='skill-pill'>⚡ {s}</span>" for s in st.session_state.active_skills])
            st.markdown(f"<div style='margin-bottom: 8px;'>{skills_html}</div>", unsafe_allow_html=True)

        # Integrated Prompt Text Area
        user_prompt_text = st.text_area(
            "Prompt",
            value=st.session_state.get("retry_prompt", ""),
            placeholder="Type @ for connectors, / for modes...",
            height=85,
            label_visibility="collapsed",
            key="main_prompt_text_area",
        )
        if "retry_prompt" in st.session_state:
            del st.session_state["retry_prompt"]

        # Toolbar Row Inside Single Card
        tb_col1, tb_col2, tb_col3, tb_col4, tb_col5, tb_col6 = st.columns([0.6, 2.2, 1.0, 2.8, 0.6, 0.6])

        with tb_col1:
            st.markdown("<div style='text-align:center; padding-top:4px;'>➕</div>", unsafe_allow_html=True)

        with tb_col2:
            search_mode_choice = st.selectbox(
                "Search",
                options=[
                    "🔍 Search (Auto Agent)",
                    "🌐 Deep research",
                    "🏛️ Model council",
                    "📖 Learn step by step",
                ],
                index=0,
                label_visibility="collapsed",
                key="card_search_mode_select",
            )

        with tb_col3:
            code_choice = st.checkbox("💻 Code", value=st.session_state.code_search_active, key="card_code_checkbox")
            st.session_state.code_search_active = code_choice

        with tb_col4:
            selected_model_choice = st.selectbox(
                "Model",
                options=[
                    "meta/llama-3.3-70b-instruct",
                    "deepseek-ai/deepseek-r1",
                    "deepseek-ai/deepseek-v3",
                    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
                    "nvidia/llama-3.1-nemotron-70b-instruct",
                    "nvidia/nemotron-4-340b-instruct",
                    "meta/llama-3.1-405b-instruct",
                    "meta/llama-3.1-70b-instruct",
                    "meta/llama-3.1-8b-instruct",
                    "meta/llama-3.2-11b-vision-instruct",
                    "meta/llama-3.2-90b-vision-instruct",
                    "mistralai/mistral-large-3-675b-instruct-2512",
                    "mistralai/mistral-large-2-instruct",
                    "mistralai/mixtral-8x22b-instruct",
                    "mistralai/mixtral-8x7b-instruct",
                    "mistralai/codestral-22b-instruct",
                    "mistralai/mistral-nemo-12b-instruct",
                    "qwen/qwen2.5-72b-instruct",
                    "qwen/qwen2.5-coder-32b-instruct",
                    "qwen/qwen2-vl-72b-instruct",
                    "google/gemma-2-27b-it",
                    "google/gemma-2-9b-it",
                    "microsoft/phi-3.5-mini-instruct",
                    "microsoft/phi-3-medium-4k-instruct",
                    "databricks/dbrx-instruct",
                ],
                index=0,
                label_visibility="collapsed",
                key="card_model_select",
            )

        with tb_col5:
            st.markdown("<div style='text-align:center; padding-top:4px;'>🎙️</div>", unsafe_allow_html=True)

        with tb_col6:
            submit_query_clicked = st.form_submit_button("⬆️", type="primary", use_container_width=True)

    # Bottom Customize & Shortcut Helper
    st.markdown("<br/>", unsafe_allow_html=True)
    c_col1, c_col2, c_col3 = st.columns([3, 3, 3])
    with c_col1:
        with st.popover("ℹ️ Shortcuts & Commands", use_container_width=True):
            st.markdown("**@ Connectors:**")
            st.caption("• `@openkb` — Vector Retrieval")
            st.caption("• `@web` — Live Brave Search")
            st.caption("• `@code` — Repository Search")
            st.markdown("** Execution Modes:**")
            st.caption("• `/research` — Deep Multi-Hop")
            st.caption("• `/council` — Multi-Model Compare")
            st.caption("• `/learn` — Step-by-Step Guide")
    with c_col2:
        if st.button("🎛️ Customize", use_container_width=True, key="btn_customize_bottom"):
            open_skills_modal()

    return user_prompt_text, search_mode_choice, selected_model_choice, submit_query_clicked
