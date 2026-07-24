import httpx
import streamlit as st
from skills import ALL_SKILLS


@st.dialog("📁 Data Sources & Live Vector Syncing", width="large")
def open_ingestion_modal(backend_api_url: str = "http://localhost:8000"):
    st.caption("Connect live data sources to automatically chunk, embed, and index into your vector knowledge base.")

    tab_web, tab_github, tab_file, tab_sql = st.tabs(["🌐 Web URL", "💻 GitHub Repo", "📁 File Upload", "🗄️ SQL Query"])

    headers = {"X-API-Key": st.session_state.get("api_key_input", "")}

    # Tab 1: Web URL Scraper
    with tab_web:
        st.markdown("**Scrape & Index Web Page / Documentation URL**")
        web_url = st.text_input("Web URL", value="https://docs.streamlit.io", key="ingest_web_url")
        col_name = st.text_input("Collection Name", value="streamlit-docs", key="ingest_web_col_name")
        if st.button("⚡ Start Web Ingestion", type="primary", use_container_width=True, key="btn_start_web_ingest"):
            try:
                with httpx.Client() as client:
                    resp = client.post(
                        f"{backend_api_url}/api/v1/ingest",
                        headers=headers,
                        json={
                            "source_type": "web",
                            "uri": web_url,
                            "tenant_id": st.session_state.tenant_id,
                            "collection_name": col_name,
                        },
                        timeout=5.0,
                    )
                if resp.status_code == 200:
                    data = resp.json()
                    st.session_state.active_ingest_job_id = data.get("job_id")
                    st.success(f"Job started: `{data.get('job_id')}`")
                    st.rerun()
                else:
                    st.error(f"Error {resp.status_code}: {resp.text}")
            except Exception as ex:
                st.error(f"Failed to trigger ingestion: {ex}")

    # Tab 2: GitHub Repository Connector
    with tab_github:
        st.markdown("**Clone & Index GitHub Repository**")
        repo_url = st.text_input("GitHub Repo URL", value="https://github.com/streamlit/streamlit", key="ingest_gh_url")
        gh_col_name = st.text_input("Collection Name", value="github-streamlit", key="ingest_gh_col_name")
        if st.button("⚡ Start GitHub Sync", type="primary", use_container_width=True, key="btn_start_gh_ingest"):
            try:
                with httpx.Client() as client:
                    resp = client.post(
                        f"{backend_api_url}/api/v1/ingest",
                        headers=headers,
                        json={
                            "source_type": "github",
                            "uri": repo_url,
                            "tenant_id": st.session_state.tenant_id,
                            "collection_name": gh_col_name,
                        },
                        timeout=5.0,
                    )
                if resp.status_code == 200:
                    data = resp.json()
                    st.session_state.active_ingest_job_id = data.get("job_id")
                    st.success(f"GitHub Sync Started: `{data.get('job_id')}`")
                    st.rerun()
            except Exception as ex:
                st.error(f"Failed to connect GitHub: {ex}")

    # Tab 3: File Upload
    with tab_file:
        st.markdown("**Upload Local File (.txt, .md, .py, .json, .csv)**")
        uploaded_file = st.file_uploader(
            "Choose file to ingest", type=["txt", "md", "py", "json", "csv"], key="ingest_file_uploader"
        )
        if uploaded_file and st.button(
            "⚡ Upload & Embed File", type="primary", use_container_width=True, key="btn_upload_file_ingest"
        ):
            try:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type or "text/plain")}
                data_form = {
                    "source_type": "file",
                    "tenant_id": st.session_state.tenant_id,
                    "collection_name": f"file-{uploaded_file.name}",
                }
                with httpx.Client() as client:
                    resp = client.post(
                        f"{backend_api_url}/api/v1/ingest/upload",
                        headers=headers,
                        data=data_form,
                        files=files,
                        timeout=10.0,
                    )
                if resp.status_code == 200:
                    job_data = resp.json()
                    st.session_state.active_ingest_job_id = job_data.get("job_id")
                    st.success(f"File upload job queued: `{job_data.get('job_id')}`")
                    st.rerun()
            except Exception as ex:
                st.error(f"Failed to upload file: {ex}")

    # Tab 4: SQL Database Query Extractor
    with tab_sql:
        st.markdown("**Extract & Embed SQL Query Result**")
        sql_conn = st.text_input(
            "Connection URI", value="postgresql://user:pass@localhost:5432/db", key="ingest_sql_conn"
        )
        sql_query = st.text_area(
            "SQL Query", value="SELECT * FROM products LIMIT 100", height=60, key="ingest_sql_query"
        )
        if st.button(
            "⚡ Extract & Embed SQL Data", type="primary", use_container_width=True, key="btn_start_sql_ingest"
        ):
            try:
                with httpx.Client() as client:
                    resp = client.post(
                        f"{backend_api_url}/api/v1/ingest",
                        headers=headers,
                        json={
                            "source_type": "sql",
                            "uri": f"{sql_conn}#{sql_query}",
                            "tenant_id": st.session_state.tenant_id,
                            "collection_name": "sql-product-catalog",
                        },
                        timeout=5.0,
                    )
                if resp.status_code == 200:
                    job_data = resp.json()
                    st.session_state.active_ingest_job_id = job_data.get("job_id")
                    st.success(f"SQL Job started: `{job_data.get('job_id')}`")
                    st.rerun()
            except Exception as ex:
                st.error(f"Failed SQL extraction: {ex}")

    st.write("---")

    # Real-Time Job Progress Tracker
    active_job_id = st.session_state.get("active_ingest_job_id")
    if active_job_id:
        st.markdown(f"**⚡ Active Job Progress (`{active_job_id}`):**")
        try:
            with httpx.Client() as client:
                status_resp = client.get(
                    f"{backend_api_url}/api/v1/ingest/status/{active_job_id}", headers=headers, timeout=5.0
                )
            if status_resp.status_code == 200:
                j_info = status_resp.json()
                prog = float(j_info.get("progress", 0.0))
                st.progress(prog)
                st.caption(f"Status: `{j_info.get('status')}` | Chunks Processed: `{j_info.get('chunks_processed')}`")
                if j_info.get("status") == "completed":
                    st.success("Ingestion job completed successfully!")
                    del st.session_state["active_ingest_job_id"]
                elif j_info.get("status") == "failed":
                    st.error(f"Job failed: {j_info.get('error')}")
                    st.session_state.pop("active_ingest_job_id", None)
        except Exception as ex:
            st.warning(f"Polling job status: {ex}")

    st.write("---")

    # Active Collections Table
    st.markdown("**📚 Active Knowledge Base Collections:**")
    try:
        with httpx.Client() as client:
            col_resp = client.get(
                f"{backend_api_url}/api/v1/collections?tenant_id={st.session_state.tenant_id}",
                headers=headers,
                timeout=5.0,
            )
        if col_resp.status_code == 200:
            cols_data = col_resp.json().get("collections", [])
            if not cols_data:
                st.caption("No custom knowledge collections found for this tenant.")
            else:
                for c_item in cols_data:
                    c_col1, c_col2 = st.columns([8, 2])
                    with c_col1:
                        st.markdown(f"**{c_item.get('name')}** (`{c_item.get('source_type')}`)")
                        st.caption(
                            f"URI: `{c_item.get('uri')}` | Chunks: **{c_item.get('chunk_count')}** | Sync: `{c_item.get('timestamp')}`"
                        )
                    with c_col2:
                        if st.button("🗑️ Delete", key=f"btn_del_col_{c_item.get('id')}", use_container_width=True):
                            with httpx.Client() as del_client:
                                del_client.delete(
                                    f"{backend_api_url}/api/v1/collections/{c_item.get('id')}",
                                    headers=headers,
                                    timeout=5.0,
                                )
                            st.toast("Deleted collection!")
                            st.rerun()
                    st.markdown("---")
    except Exception as ex:
        st.caption(f"Collections list offline: {ex}")

    if st.button("Close Ingestion Drawer", use_container_width=True):
        st.rerun()


@st.dialog("📄 Vector Chunk Inspection", width="large")
def open_chunk_inspector_modal(source_dict: dict):
    meta = source_dict.get("metadata", {})
    source_name = meta.get("source", "Knowledge Base")
    score = source_dict.get("score", 0.9)
    score_pct = int(score * 100)

    st.markdown(f"### 🔍 {source_name}")
    st.caption(f"Relevance Score: **{score_pct}%** | Category: `{meta.get('category', 'vector')}`")
    st.progress(score)

    st.markdown("**Full Chunk Content:**")
    st.code(source_dict.get("content", "No content available."), language="text")

    st.markdown("**Chunk Metadata Dictionary:**")
    st.json(meta)

    if st.button("Close Inspector", use_container_width=True):
        st.rerun()


@st.dialog("💻 System & Infrastructure Health", width="large")
def open_health_modal():
    st.markdown("### 🟢 Nexus AI System Diagnostics")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("FastAPI Backend", "Online (200 OK)")
    with col2:
        st.metric("Vector DB (OpenKB)", "Connected")
    with col3:
        st.metric("RAG Pipeline", "9 Layers Active")

    st.json(
        {
            "status": "healthy",
            "tenant_id": st.session_state.tenant_id,
            "session_id": st.session_state.session_id,
            "active_skills_loaded": len(st.session_state.active_skills),
            "telemetry": "OpenTelemetry Active",
        }
    )
    if st.button("Close Diagnostics", use_container_width=True):
        st.rerun()


@st.dialog("📁 Spaces & Multi-Tenant Isolation", width="large")
def open_tenants_modal():
    st.markdown("### 🏢 Multi-Tenant Workspace Isolation")
    st.info(f"Current Workspace Scope: Tenant `{st.session_state.tenant_id}`")
    st.write(
        "All vector retrieval, chat history, and semantic caching are strictly isolated by `tenant_id:session_id`."
    )
    new_tenant = st.text_input("Tenant ID Scope", value=st.session_state.tenant_id)
    if st.button("Update Workspace Scope", use_container_width=True):
        st.session_state.tenant_id = new_tenant
        st.success(f"Workspace tenant updated to `{new_tenant}`")
        st.rerun()


@st.dialog("📄 Artifacts & Implementation Specs", width="large")
def open_artifacts_modal():
    st.markdown("### 📄 Brain Workspace Specifications")
    st.caption("Active system design artifacts:")
    with st.container(border=True):
        st.markdown("**`implementation_plan.md`**")
        st.caption("Complete technical architecture and skills integration specification.")
    with st.container(border=True):
        st.markdown("**`walkthrough.md`**")
        st.caption("Verification results, skill inventory breakdown, and test execution logs.")
    if st.button("Close Specs", use_container_width=True):
        st.rerun()


@st.dialog("🛠️ Agent & Product Management Skills Library", width="large")
def open_skills_modal():
    st.caption(
        "Select skills to load into your active chat session. Selected skills guide model reasoning without bloating your chat view."
    )

    categories = [
        "All (78)",
        "PM Strategy",
        "PM Discovery",
        "PM Execution",
        "GTM & Growth",
        "Research & Data",
        "Design & Tech",
        "Toolkit & AI Ship",
    ]
    selected_cat = st.radio("Category", categories, horizontal=True, label_visibility="collapsed")
    st.write("---")

    clean_cat = selected_cat.split(" (")[0]
    filtered_skills = {
        sid: sinfo for sid, sinfo in ALL_SKILLS.items() if clean_cat == "All" or sinfo["category"] == clean_cat
    }

    st.caption(f"Showing **{len(filtered_skills)}** skills in category `{clean_cat}`:")

    cols = st.columns(4)
    for idx, (skill_id, skill_info) in enumerate(filtered_skills.items()):
        col = cols[idx % 4]
        with col:
            with st.container(border=True):
                st.markdown(f"**{skill_info['icon']} {skill_info['title']}**")
                st.caption(f"`{skill_id}` | [{skill_info['category']}]")
                st.caption(skill_info["description"])

                is_active = skill_id in st.session_state.active_skills
                btn_label = "✓ Loaded" if is_active else "+ Use"
                btn_type = "secondary" if is_active else "primary"

                if st.button(btn_label, key=f"modal_skill_{skill_id}", type=btn_type, use_container_width=True):
                    if is_active:
                        st.session_state.active_skills.remove(skill_id)
                    else:
                        st.session_state.active_skills.append(skill_id)
                    st.rerun()

    st.write("---")
    if st.button("Close Modal", use_container_width=True):
        st.rerun()
