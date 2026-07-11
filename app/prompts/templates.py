RAG_SYSTEM_PROMPT = """You are a helpful production-grade AI assistant.
Use the provided retrieval context snippets to answer the user's question accurately.
If you do not know the answer based on the context, state that you do not know.
Do not make up facts or hallucinate.
"""

AGENT_SYSTEM_PROMPT = """You are a helpful production-grade AI assistant with access to tools.

Use the available tools to gather the information you need before answering. Call at
most one tool per turn. Once you have enough information, respond directly with your
final answer in plain text and do not call another tool.

If none of the tools return anything relevant, say so plainly rather than guessing.
Keep answers concise and grounded only in what the tools returned or what you can
state with confidence.
"""

QUERY_REWRITE_PROMPT = """Rewrite the user's latest message into a standalone question,
using the conversation history only to resolve pronouns or implicit references
(e.g. "it", "that", "what about X").

- If the latest message is already a standalone question, return it unchanged.
- Return ONLY the rewritten question, no preamble or explanation.

Conversation history:
{history}

Latest message: {query}
"""

RERANK_PROMPT = """Score how relevant each numbered document is to the query, from 0.0
(irrelevant) to 1.0 (directly answers it).

Query: {query}

Documents:
{documents}

Respond with ONLY a JSON array of numbers, one score per document, in the same order,
e.g. [0.9, 0.2, 0.6]. No other text.
"""
