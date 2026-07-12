import json
import logging
from typing import Dict, List, Tuple, Union

from langsmith import traceable
from openai.types.chat import ChatCompletion, ChatCompletionMessageFunctionToolCall

from app.agents.tools.registry import tool_registry
from app.models import SearchDocument
from app.prompts.registry import prompt_registry
from app.security.content_filter import content_filter
from app.security.resilience import CircuitBreakerOpenException, llm_breaker, search_tool_breaker
from app.services.context_manager import context_manager
from app.services.hooks import lifecycle_hooks
from app.services.llm_client import LLMClient, llm_client
from app.services.state_store import state_store
from app.types import (
    AgentExecutionResult,
    AgentTrajectoryStep,
    ChatMessage,
    JSONValue,
    TokenUsage,
    ToolCall,
)

logger = logging.getLogger("app.agents.executor")

# Token budget applied to any single tool call's results before they're added to
# the agent's running context, so one chatty tool can't blow out the LLM's window.
PER_TOOL_CALL_TOKEN_BUDGET = 800

_FALLBACK_ANSWER = (
    "I'm temporarily unable to reach the language model to answer this "
    "(the LLM service circuit breaker is open after repeated failures). "
    "Please try again shortly."
)


class AgentExecutor:
    def __init__(self, max_turns: int = 5):
        self.max_turns = max_turns
        logger.info(f"Agent Executor initialized with max_turns={max_turns}")

    @traceable(name="AgentExecutor.execute_trajectory", run_type="chain")
    async def execute_trajectory(
        self, session_id: str, query: str, actor_permission: str = "low"
    ) -> AgentExecutionResult:
        await lifecycle_hooks.emit("on_agent_start", session_id=session_id, query=query)

        # 1. State Store Checkpoint Recovery (S - Pitfall Mitigation)
        checkpoint = await state_store.load_checkpoint(session_id)
        messages: List[ChatMessage]
        if checkpoint:
            logger.info(f"Checkpoint recovered for session '{session_id}' at step {checkpoint['current_step']}.")
            step_count = checkpoint["current_step"]
            agent_state = checkpoint["state"]
            trajectory = checkpoint["trajectory"]
            messages = agent_state.get("messages", [])
        else:
            step_count = 0
            agent_state = {"query": query, "completed": False}
            trajectory = []
            system_prompt = await prompt_registry.get_prompt("agent_system_prompt")
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ]

        # NOTE: retrieved_documents is intentionally NOT checkpointed (only the
        # string-form trajectory/messages are, to keep checkpoint payloads simple
        # and JSON-safe). If a process crashes mid-loop and resumes from a
        # checkpoint, structured documents from turns before the crash won't be
        # in the final sources list, only the ones from turns after resume. The
        # agent's own reasoning is unaffected (it resumes from the full message
        # history either way) - this only narrows source attribution in that
        # specific crash-and-resume edge case.
        retrieved_documents: List[SearchDocument] = []
        prompt_token_usage: TokenUsage = {"prompt_tokens": 0, "completion_tokens": 0}
        tools = LLMClient.tool_registry_schemas_to_openai_tools(tool_registry.get_tool_schemas())

        while step_count < self.max_turns and not agent_state.get("completed"):
            step_count += 1
            is_final_turn = step_count >= self.max_turns
            logger.info(f"Executing Agent Turn {step_count}/{self.max_turns}")

            await lifecycle_hooks.emit("on_llm_call", session_id=session_id, step=step_count)

            try:
                response: ChatCompletion = await llm_breaker.call(
                    llm_client.chat,
                    messages,
                    tools=None if is_final_turn else tools,
                    tool_choice=("none" if is_final_turn else "auto"),
                )
            except Exception as e:
                logger.error(f"LLM call failed for session '{session_id}': {e}")
                trajectory.append(
                    {
                        "turn": step_count,
                        "thought": "LLM unavailable.",
                        "tool": None,
                        "arguments": {},
                        "observation": str(e),
                    }
                )
                agent_state["completed"] = True
                agent_state["final_answer"] = _FALLBACK_ANSWER
                await lifecycle_hooks.emit("on_error", session_id=session_id, error=e)
                break

            choice_message = response.choices[0].message
            if response.usage:
                prompt_token_usage["prompt_tokens"] += response.usage.prompt_tokens
                prompt_token_usage["completion_tokens"] += response.usage.completion_tokens

            await lifecycle_hooks.emit(
                "on_llm_end", session_id=session_id, step=step_count, thought=choice_message.content
            )

            tool_calls = choice_message.tool_calls

            step_record: AgentTrajectoryStep
            if tool_calls:
                call = tool_calls[0]  # single tool per turn, matches tool_registry's one-call execution model
                if not isinstance(call, ChatCompletionMessageFunctionToolCall):
                    # The model asked for OpenAI's newer "custom tool" format, which
                    # nothing in tool_registry.py supports (every registered tool
                    # uses the standard function-calling schema) - treat it as a
                    # dead end for this turn rather than crashing on .function,
                    # which only exists on the function-call variant.
                    logger.warning(f"Unsupported tool call type '{call.type}' from model; skipping.")
                    trajectory.append(
                        {
                            "turn": step_count,
                            "thought": choice_message.content or "",
                            "tool": None,
                            "arguments": {},
                            "observation": f"Unsupported tool call type: {call.type}",
                        }
                    )
                    continue

                action_tool = call.function.name
                action_args: JSONValue
                try:
                    action_args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    action_args = {}
                if not isinstance(action_args, dict):
                    action_args = {}

                assistant_tool_call: ToolCall = {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.function.name, "arguments": call.function.arguments},
                }
                messages.append(
                    {
                        "role": "assistant",
                        "content": choice_message.content,
                        "tool_calls": [assistant_tool_call],
                    }
                )

                await lifecycle_hooks.emit(
                    "on_tool_execute", session_id=session_id, tool_name=action_tool, args=action_args
                )
                observation, docs_from_tool = await self._execute_tool_call(action_tool, action_args, actor_permission)
                retrieved_documents.extend(docs_from_tool)

                messages.append({"role": "tool", "tool_call_id": call.id, "content": observation})

                step_record = {
                    "turn": step_count,
                    "thought": choice_message.content or "",
                    "tool": action_tool,
                    "arguments": action_args,
                    "observation": observation,
                }
            else:
                final_text = choice_message.content or "I don't have enough information to answer that."
                messages.append({"role": "assistant", "content": final_text})
                agent_state["completed"] = True
                agent_state["final_answer"] = final_text
                step_record = {
                    "turn": step_count,
                    "thought": final_text,
                    "tool": None,
                    "arguments": {},
                    "observation": "",
                }

            trajectory.append(step_record)
            agent_state["messages"] = messages
            await state_store.save_checkpoint(session_id, step_count, agent_state, trajectory)

        # Handle termination edge-case: forced final turn (tool_choice="none")
        # above guarantees a final_answer gets set before max_turns is hit, but
        # keep this as a defensive backstop in case that ever changes.
        if not agent_state.get("completed"):
            logger.warning(f"Agent terminated: Exceeded max turn limit ({self.max_turns}) for query: '{query}'")
            agent_state["completed"] = True
            agent_state.setdefault(
                "final_answer",
                "I wasn't able to reach a final answer within the allotted reasoning steps.",
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

        await state_store.clear_checkpoint(session_id)

        return {
            "trajectory": trajectory,
            "completed": agent_state.get("completed", False),
            "final_answer": agent_state.get("final_answer", _FALLBACK_ANSWER),
            "retrieved_documents": retrieved_documents,
            "token_usage": prompt_token_usage,
        }

    async def _execute_tool_call(
        self, action_tool: str, action_args: Dict[str, JSONValue], actor_permission: str
    ) -> Tuple[str, List[SearchDocument]]:
        """
        Runs one tool call, then applies content filtering, relevance grading, and
        token-budget packing to whatever it returns before it becomes part of the
        agent's context - so a tool result reaches the LLM already sanitized,
        graded, and budgeted rather than raw.
        """
        try:
            raw_result: Union[str, List[SearchDocument]] = await search_tool_breaker.call(
                tool_registry.execute_tool, action_tool, action_args, actor_permission
            )
        except CircuitBreakerOpenException as e:
            logger.error(f"Circuit Breaker open for search tools: {e}")
            return f"Tool execution blocked by circuit breaker: {e}", []
        except Exception as e:
            logger.error(f"Error executing tool '{action_tool}': {e}")
            return f"Tool execution failed: {e}", []

        if isinstance(raw_result, str):
            # Tool returned something other than documents (e.g. a permission-denied string).
            return raw_result, []

        docs: List[SearchDocument] = raw_result
        docs = await content_filter.filter_contexts(docs)

        from app.agents.document_grader import document_grader

        query_arg = action_args.get("query", "")
        if isinstance(query_arg, str) and query_arg:
            docs = await document_grader.grade_documents(query_arg, docs)
        docs = await context_manager.pack_context(docs, token_budget=PER_TOOL_CALL_TOKEN_BUDGET)

        observation = (
            "\n".join(f"[{d.metadata.get('source', 'unknown')}] {d.content}" for d in docs) or "No results found."
        )
        return observation, docs


agent_executor = AgentExecutor()
