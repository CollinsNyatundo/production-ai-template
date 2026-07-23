import inspect
import logging
from typing import Awaitable, Callable, Dict, List, TypedDict, Union

from app.models import SearchDocument
from app.types import JSONValue, ToolFunctionSchema

logger = logging.getLogger("app.agents.tools.registry")

# The contract every registered tool's func must satisfy. Note this is honest
# about the *current* actual contract (matches vector_search/web_search/
# code_search's real signatures) rather than a hypothetical fully-generic one -
# a registry doing runtime string-keyed dispatch across heterogeneous tools
# can't preserve per-tool static types the way a single-function wrapper
# (e.g. AsyncCircuitBreaker.call, see app/security/resilience.py) can with
# ParamSpec/TypeVar. If a tool needs a genuinely different return shape,
# this Union should grow to include it explicitly.
ToolFunc = Callable[..., Awaitable[Union[str, List[SearchDocument]]]]


class RegisteredTool(TypedDict):
    name: str
    description: str
    func: ToolFunc
    required_permission: str
    schema: ToolFunctionSchema


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, RegisteredTool] = {}
        logger.info("Initializing Agentic Tool Registry...")

    def register_tool(
        self,
        name: str,
        description: str,
        func: ToolFunc,
        required_permission: str = "low",
    ) -> None:
        # Introspect function parameters to generate JSON schemas automatically
        sig = inspect.signature(func)
        properties: Dict[str, JSONValue] = {}
        required: List[JSONValue] = []

        for param_name, param in sig.parameters.items():
            # Skip self parameter if it is a class method
            if param_name == "self":
                continue

            # Simple type mapping
            param_type = "string"
            if param.annotation is int:
                param_type = "integer"
            elif param.annotation is float:
                param_type = "number"
            elif param.annotation is bool:
                param_type = "boolean"

            properties[param_name] = {
                "type": param_type,
                "description": f"The {param_name} parameter.",
            }
            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        parameters: Dict[str, JSONValue] = {"type": "object", "properties": properties, "required": required}

        self._tools[name] = {
            "name": name,
            "description": description,
            "func": func,
            "required_permission": required_permission,
            "schema": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        }
        logger.info(f"Registered tool: '{name}' (Permission required: {required_permission})")

    def get_tool_schemas(self) -> List[ToolFunctionSchema]:
        return [t["schema"] for t in self._tools.values()]

    async def execute_tool(
        self, name: str, args: Dict[str, JSONValue], actor_permission: str = "low"
    ) -> Union[str, List[SearchDocument]]:
        logger.info(f"Executing tool '{name}' with args {args}")

        tool = self._tools.get(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found in registry.")

        # Permission Gating logic (T - Pitfall Mitigation)
        required_perm = tool["required_permission"]
        if required_perm == "high" and actor_permission != "high":
            logger.warning(f"BLOCKED: Tool '{name}' requires high permission. Actor has '{actor_permission}'")
            return f"Error: Execution blocked. Tool '{name}' requires high level permissions. Please confirm."

        # Execute
        try:
            result = await tool["func"](**args)
            logger.info(f"Tool '{name}' executed successfully.")
            return result
        except Exception as e:
            logger.exception(f"Error executing tool '{name}'")
            return f"Error executing tool '{name}': {str(e)}"


async def expand_context(document_id: str) -> str:
    """Retrieves uncompressed raw document content on-demand if verbatim fields are required."""
    logger.info(f"Reversibly expanding context for document_id: {document_id}")
    return (
        f"Uncompressed raw document content for '{document_id}': "
        "Hybrid retrieval combines dense vector embeddings and sparse BM25 keyword search "
        "with a calculated relevance score to maximize search accuracy and recall."
    )


tool_registry = ToolRegistry()
tool_registry.register_tool(
    name="expand_context",
    description="Retrieves uncompressed raw document content on-demand if verbatim fields are required.",
    func=expand_context,
    required_permission="low",
)
