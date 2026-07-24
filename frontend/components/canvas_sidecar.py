import streamlit as st


def render_canvas_sidecar():
    if not st.session_state.get("canvas_open", False):
        return

    artifact = st.session_state.get(
        "active_canvas_artifact",
        {
            "title": "Untitled Artifact",
            "content": "No content selected.",
            "language": "markdown",
            "filename": "artifact.txt",
        },
    )

    with st.container(border=True):
        # Header Row
        head_col1, head_col2 = st.columns([8, 2])
        with head_col1:
            st.markdown(f"### 📄 {artifact.get('title', 'Canvas Artifact')}")
            st.caption(f"Language: `{artifact.get('language', 'text')}`")
        with head_col2:
            if st.button("❌ Close", key="btn_close_canvas", use_container_width=True):
                st.session_state.canvas_open = False
                st.rerun()

        st.write("---")

        # Actions Toolbar
        act_col1, act_col2 = st.columns([5, 5])
        with act_col1:
            st.download_button(
                label="📥 Download File",
                data=artifact.get("content", ""),
                file_name=artifact.get("filename", "artifact.txt"),
                mime="text/plain",
                use_container_width=True,
                key="btn_download_canvas_artifact",
            )
        with act_col2:
            if st.button("📋 Copy Content", key="btn_copy_canvas_artifact", use_container_width=True):
                st.toast("Copied artifact content to clipboard!")

        st.write("---")

        # Content Viewer
        lang = artifact.get("language", "markdown").lower()
        content = artifact.get("content", "")
        if lang in ["python", "json", "bash", "sh", "javascript", "typescript", "html", "css", "yaml"]:
            st.code(content, language=lang)
        else:
            st.markdown(content)
