"""
Shared type definitions. Exists specifically so the rest of the codebase can
comply with CLAUDE.md's "do not use Any" rule without every module inventing
its own ad-hoc TypedDicts for the same handful of recurring shapes (chat
messages, tool schemas, trajectory steps, checkpoint state).

Where a value is genuinely arbitrary JSON (tool call arguments, document
metadata), JSONValue is used - this is still meaningfully more precise than
Any: mypy will reject e.g. calling a string method on a JSONValue without a
type-narrowing check first, whereas Any disables checking entirely.
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional, TypedDict, Union

if TYPE_CHECKING:
    from app.models import SearchDocument

JSONPrimitive = Union[str, int, float, bool, None]
JSONValue = Any


# ---------------------------------------------------------------------------
# OpenAI/NVIDIA chat message + tool-calling shapes
# ---------------------------------------------------------------------------
class ToolCallFunction(TypedDict):
    name: str
    arguments: str  # JSON-encoded string, per the OpenAI tool-calling wire format


class ToolCall(TypedDict):
    id: str
    type: str
    function: ToolCallFunction


class ChatMessage(TypedDict, total=False):
    """total=False because different roles use different subsets of fields:
    system/user use content only; assistant may add tool_calls; tool messages
    use tool_call_id instead of role-appropriate content alone."""

    role: str
    content: Optional[str]
    tool_calls: List[ToolCall]
    tool_call_id: str


class ToolFunctionSchema(TypedDict):
    name: str
    description: str
    parameters: Dict[str, JSONValue]


class ToolSchema(TypedDict):
    type: str
    function: ToolFunctionSchema


# ---------------------------------------------------------------------------
# Headroom Context Compression & Reversible Storage
# ---------------------------------------------------------------------------
class HeadroomCompressedPayload(TypedDict):
    doc_id: str
    original_token_count: int
    compressed_token_count: int
    compressed_content: str
    compression_ratio: float
    is_reversible: bool


class ExpandContextArgs(TypedDict):
    document_id: str


class ExpandContextResult(TypedDict):
    document_id: str
    content: str
    status: str


# ---------------------------------------------------------------------------
# Agent execution
# ---------------------------------------------------------------------------
class TokenUsage(TypedDict):
    prompt_tokens: int
    completion_tokens: int


class AgentTrajectoryStep(TypedDict):
    turn: int
    thought: str
    tool: Optional[str]
    arguments: Dict[str, JSONValue]
    observation: str


class AgentCheckpointState(TypedDict, total=False):
    query: str
    completed: bool
    messages: List[ChatMessage]
    final_answer: str
    token_usage: TokenUsage


class CheckpointRecord(TypedDict):
    current_step: int
    state: AgentCheckpointState
    trajectory: List[AgentTrajectoryStep]


class AgentExecutionResult(TypedDict):
    trajectory: List[AgentTrajectoryStep]
    completed: bool
    final_answer: str
    retrieved_documents: List["SearchDocument"]
    token_usage: TokenUsage


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------
OTelAttributeValue = Union[str, bool, int, float]


class UserContext(TypedDict):
    username: str
    role: str
    tenant_id: str
    app_env: str


# ---------------------------------------------------------------------------
# Infra
# ---------------------------------------------------------------------------
class EngineKwargs(TypedDict, total=False):
    echo: bool
    pool_pre_ping: bool
    poolclass: object
    pool_size: int
    max_overflow: int
    connect_args: Dict[str, JSONValue]
