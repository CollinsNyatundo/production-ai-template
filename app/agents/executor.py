import logging
from typing import Any, Dict

from app.agents.tools.registry import tool_registry
from app.security.resilience import CircuitBreakerOpenException, search_tool_breaker
from app.services.hooks import lifecycle_hooks
from app.services.state_store import state_store

logger = logging.getLogger("app.agents.executor")


class AgentExecutor:
    def __init__(self, max_turns: int = 5):
        self.max_turns = max_turns
        logger.info(f"Agent Executor initialized with max_turns={max_turns}")

    async def execute_trajectory(
        self, session_id: str, query: str, actor_permission: str = "low"
    ) -> Dict[str, Any]:
        # Emit event
        await lifecycle_hooks.emit("on_agent_start", session_id=session_id, query=query)

        # 1. State Store Checkpoint Recovery (S - Pitfall Mitigation)
        checkpoint = await state_store.load_checkpoint(session_id)
        if checkpoint:
            logger.info(
                f"Checkpoint recovered for session '{session_id}' at step {checkpoint['current_step']}."
            )
            step_count = checkpoint["current_step"]
            agent_state = checkpoint["state"]
            trajectory = checkpoint["trajectory"]
        else:
            step_count = 0
            agent_state = {"query": query, "completed": False}
            trajectory = []

        # 2. ReAct Execution Loop (E - Gap Mitigation)
        while step_count < self.max_turns and not agent_state.get("completed"):
            step_count += 1
            logger.info(f"Executing Agent Turn {step_count}/{self.max_turns}")

            # Simulated Agent Thought and Decision
            # In production, call LLM with system instructions, current state, tools schema, and trajectory
            await lifecycle_hooks.emit(
                "on_llm_call", session_id=session_id, step=step_count
            )

            # Mock reasoning steps:
            if step_count == 1:
                thought = "I need to query the vector database to search for hybrid retrieval architecture documents."
                action_tool = "vector_search"
                action_args = {"query": query}
            elif step_count == 2:
                thought = "I should check if there's any file-specific schema definitions in the repository code."
                action_tool = "code_search"
                action_args = {"query": "config"}
            else:
                thought = "I have collected enough context to answer the user query."
                action_tool = None
                action_args = {}
                agent_state["completed"] = True

            # Trigger LLM call hook finish
            await lifecycle_hooks.emit(
                "on_llm_end", session_id=session_id, step=step_count, thought=thought
            )

            # 3. Tool Execution
            observation = ""
            if action_tool:
                await lifecycle_hooks.emit(
                    "on_tool_execute",
                    session_id=session_id,
                    tool_name=action_tool,
                    args=action_args,
                )
                try:
                    # Wrap tool execution in circuit breaker to protect against downstream tool API downtime
                    observation_raw = await search_tool_breaker.call(
                        tool_registry.execute_tool,
                        action_tool,
                        action_args,
                        actor_permission,
                    )
                    # Convert search objects to readable text
                    if isinstance(observation_raw, list):
                        observation = "\n".join(
                            [doc.content for doc in observation_raw]
                        )
                    else:
                        observation = str(observation_raw)
                except CircuitBreakerOpenException as e:
                    observation = f"Tool execution blocked by circuit breaker: {str(e)}"
                    logger.error(f"Circuit Breaker open for search tools: {e}")
                except Exception as e:
                    await lifecycle_hooks.emit(
                        "on_error", session_id=session_id, error=e
                    )
                    observation = f"Tool execution failed: {str(e)}"
                    logger.error(f"Error executing tool in loop: {e}")

            # Append step to trajectory (V - Gap Mitigation)
            step_record = {
                "turn": step_count,
                "thought": thought,
                "tool": action_tool,
                "arguments": action_args,
                "observation": observation,
            }
            trajectory.append(step_record)

            # 4. Checkpoint saving to State Store after every step
            await state_store.save_checkpoint(
                session_id, step_count, agent_state, trajectory
            )

        # Handle termination edge-case (E - Gap Mitigation)
        if step_count >= self.max_turns and not agent_state.get("completed"):
            logger.warning(
                f"Agent terminated: Exceeded max turn limit ({self.max_turns}) for query: '{query}'"
            )
            trajectory.append(
                {
                    "turn": step_count,
                    "thought": "Max turns reached without completing goal.",
                    "tool": None,
                    "arguments": {},
                    "observation": "System safety termination.",
                }
            )

        # Clear checkpoint on success
        if agent_state.get("completed"):
            await state_store.clear_checkpoint(session_id)

        return {
            "trajectory": trajectory,
            "completed": agent_state.get("completed", False),
        }


agent_executor = AgentExecutor()
