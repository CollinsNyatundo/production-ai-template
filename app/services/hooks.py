import logging
import asyncio
from typing import Dict, List, Callable, Any

logger = logging.getLogger("app.services.hooks")

class LifecycleHooks:
    def __init__(self):
        # Dictionary mapping event names to list of subscriber callbacks
        self._subscribers: Dict[str, List[Callable[..., Any]]] = {
            "on_agent_start": [],
            "on_tool_execute": [],
            "on_llm_call": [],
            "on_llm_end": [],
            "on_error": []
        }
        logger.info("Initializing Lifecycle Hooks Registry...")

    def register(self, event: str, callback: Callable[..., Any]) -> None:
        if event not in self._subscribers:
            self._subscribers[event] = []
        self._subscribers[event].append(callback)
        logger.info(f"Registered subscriber for lifecycle event: '{event}'")

    async def emit(self, event: str, **kwargs: Any) -> None:
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
