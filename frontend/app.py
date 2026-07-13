import os

import httpx
import streamlit as st

# Styling configuration
st.set_page_config(
    page_title="Enterprise AI Interface",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Dark premium theme styles
st.markdown(
    """
<style>
    .reportview-container {
        background: #0e1117;
        color: #fafafa;
    }
    .metric-card {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 15px;
        text-align: center;
    }
</style>
""",
    unsafe_allow_html=True,
)

# Config
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000")

st.title("🤖 Production-Ready AI Application Template")
st.caption("A premium UI connected to a 9-layer decoupled RAG & agentic backend.")

# Sidebar setup
st.sidebar.header("Configuration")
session_id = st.sidebar.text_input("Session ID", value="prod-session-001")
use_cache = st.sidebar.checkbox("Enable Semantic Cache", value=True)

# API key: pre-filled from FRONTEND_API_KEY env var if the operator set one
# (e.g. via docker-compose), otherwise left blank. Previously this UI sent no
# credentials at all and only worked because of the backend's dev-mode
# unauthenticated-admin fallback - if that's ever locked down for a real
# deployment, an unauthenticated UI breaks with 401s on every request.
api_key = st.sidebar.text_input(
    "API Key",
    value=os.getenv("FRONTEND_API_KEY", ""),
    type="password",
    help="X-API-Key sent with every request. Leave blank to rely on the backend's "
    "dev-mode fallback (only works when the backend is running with APP_ENV=development).",
)
if api_key:
    st.sidebar.success("🔑 Authenticated requests")
else:
    st.sidebar.warning("⚠️ No API key set - relying on backend dev-mode fallback")


def _headers() -> dict:
    return {"X-API-Key": api_key} if api_key else {}


if st.sidebar.button("Clear Conversation"):
    try:
        with httpx.Client() as client:
            clear_response = client.delete(
                f"{BACKEND_API_URL}/api/session/{session_id}",
                headers=_headers(),
                timeout=10.0,
            )
        if clear_response.status_code == 200:
            st.sidebar.success("Conversation history cleared.")
        else:
            st.sidebar.error(f"Failed to clear ({clear_response.status_code}): {clear_response.text}")
    except Exception as e:
        st.sidebar.error(f"Failed to reach backend: {e}")

# Query input
query_input = st.text_input(
    "Ask a technical question about your architecture:",
    placeholder="What is semantic caching?",
)

if query_input:
    with st.spinner("Processing request through 9-layer pipeline..."):
        try:
            # Connect to backend
            with httpx.Client() as client:
                response = client.post(
                    f"{BACKEND_API_URL}/api/query",
                    headers=_headers(),
                    json={
                        "query": query_input,
                        "session_id": session_id,
                        "use_cache": use_cache,
                    },
                    timeout=15.0,
                )

            if response.status_code == 200:
                data = response.json()

                # Metrics Row
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(
                        f"<div class='metric-card'>⏱️ Latency<br/><b>{data.get('latency_ms', 0.0):.2f} ms</b></div>",
                        unsafe_allow_html=True,
                    )
                with col2:
                    cache_status = "HIT (Saved Cost)" if data.get("cached") else "MISS"
                    st.markdown(
                        f"<div class='metric-card'>💾 Semantic Cache<br/><b>{cache_status}</b></div>",
                        unsafe_allow_html=True,
                    )
                with col3:
                    st.markdown(
                        "<div class='metric-card'>📈 Status<br/><b>Pipeline Success</b></div>",
                        unsafe_allow_html=True,
                    )

                st.write("---")

                # Answer display
                st.subheader("Response")
                st.info(data.get("answer"))

                # Sources display
                st.subheader("Retrieved Context Sources")
                sources = data.get("sources", [])
                if sources:
                    for i, src in enumerate(sources):
                        with st.expander(
                            f"Source {i + 1}: {src.get('metadata', {}).get('source', 'Unknown')} (Score: {src.get('score'):.2f})"
                        ):
                            st.write(src.get("content"))
                else:
                    st.warning("No context sources were retrieved or needed.")
            elif response.status_code == 401:
                st.error(
                    "401 Unauthorized - set a valid API Key in the sidebar (see DEMO_API_KEYS in app/security/auth.py for local testing)."
                )
            else:
                st.error(f"Error {response.status_code}: {response.text}")

        except Exception as e:
            st.error(f"Failed to connect to backend service at {BACKEND_API_URL}. Details: {e}")
