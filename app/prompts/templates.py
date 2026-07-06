RAG_SYSTEM_PROMPT = """You are a helpful production-grade AI assistant. 
Use the provided retrieval context snippets to answer the user's question accurately.
If you do not know the answer based on the context, state that you do not know. 
Do not make up facts or hallucinate.
"""

SUMMARY_PROMPT = """Summarize the following text briefly in under two sentences.
Text: {text}
"""
