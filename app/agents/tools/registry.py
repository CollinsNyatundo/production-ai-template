import inspect
import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger("app.agents.tools.registry")


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}
        logger.info("Initializing Agentic Tool Registry...")

    def register_tool(
        self,
        name: str,
        description: str,
        func: Callable,
        required_permission: str = "low",
    ) -> None:
        # Introspect function parameters to generate JSON schemas automatically
        sig = inspect.signature(func)
        parameters = {"type": "object", "properties": {}, "required": []}

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

            parameters["properties"][param_name] = {
                "type": param_type,
                "description": f"The {param_name} parameter.",
            }
            if param.default == inspect.Parameter.empty:
                parameters["required"].append(param_name)

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

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [t["schema"] for t in self._tools.values()]

    async def execute_tool(self, name: str, args: Dict[str, Any], actor_permission: str = "low") -> Any:
        logger.info(f"Executing tool '{name}' with args {args}")

        tool = self._tools.get(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found in registry.")

        # Permission Gating logic (T - Pitfall Mitigation)
        required_perm = tool["required_permission"]
        if required_perm == "high" and actor_permission != "high":
            # Simulate rejection or request for user-in-the-loop authorization
            logger.warning(f"BLOCKED: Tool '{name}' requires high permission. Actor has '{actor_permission}'")
            return f"Error: Execution blocked. Tool '{name}' requires high level permissions. Please confirm."

        # Execute
        try:
            func = tool["func"]
            if inspect.iscoroutinefunction(func):
                result = await func(**args)
            else:
                result = func(**args)
            logger.info(f"Tool '{name}' executed successfully.")
            return result
        except Exception as e:
            logger.exception(f"Error executing tool '{name}'")
            return f"Error executing tool '{name}': {str(e)}"


tool_registry = ToolRegistry()
