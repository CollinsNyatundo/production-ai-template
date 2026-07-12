import asyncio
import logging
from typing import Callable, Dict, List

logger = logging.getLogger("app.services.hooks")


class LifecycleHooks:
    def __init__(self):
        # Dictionary mapping event names to list of subscriber callbacks.
        # Callback return values are never used (fire-and-forget pub/sub), so
        # `object` (not Any) is correct here: it accepts any return type while
        # still preventing us from accidentally relying on one.
        self._subscribers: Dict[str, List[Callable[..., object]]] = {
            "on_agent_start": [],
            "on_tool_execute": [],
            "on_llm_call": [],
            "on_llm_end": [],
            "on_error": [],
        }
        logger.info("Initializing Lifecycle Hooks Registry...")

    def register(self, event: str, callback: Callable[..., object]) -> None:
        if event not in self._subscribers:
            self._subscribers[event] = []
        self._subscribers[event].append(callback)
        logger.info(f"Registered subscriber for lifecycle event: '{event}'")

    async def emit(self, event: str, **kwargs: object) -> None:
        # kwargs are genuinely heterogeneous across call sites (session_id: str,
        # step: int, error: Exception, args: dict, ...) - object is the honest
        # type for "accepts anything," not Any, since subscribers still have to
        # narrow before using a specific field's type.
        logger.info(f"Emitting lifecycle event: '{event}' (Args: {list(kwargs.keys())})")
        callbacks = self._subscribers.get(event, [])

        # Execute callbacks concurrently using asyncio.gather
        tasks = []
        for cb in callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    tasks.append(cb(**kwargs))
                else:
                    # Run sync callbacks in separate executor thread
                    tasks.append(asyncio.to_thread(cb, **kwargs))
            except Exception as e:
                logger.error(f"Error preparing callback for event '{event}': {e}")

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


lifecycle_hooks = LifecycleHooks()
