import asyncio
import logging
import time
from typing import Any, Callable

from app.config import settings

logger = logging.getLogger("app.security.resilience")


class CircuitBreakerOpenException(Exception):
    """Exception raised when the circuit breaker is in OPEN state."""

    pass


class AsyncCircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = settings.circuit_breaker_failure_threshold,
        recovery_timeout: float = settings.circuit_breaker_recovery_timeout,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        self.last_failure_time = 0.0
        logger.info(
            f"Circuit Breaker '{name}' initialized (threshold={failure_threshold}, timeout={recovery_timeout}s)"
        )

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        current_time = time.time()

        # 1. State check
        if self.state == "OPEN":
            # Check if recovery timeout has expired to transition to HALF-OPEN
            if current_time - self.last_failure_time >= self.recovery_timeout:
                logger.warning(
                    f"Circuit Breaker '{self.name}' transitioning from OPEN to HALF-OPEN (recovery timeout expired)"
                )
                self.state = "HALF-OPEN"
            else:
                logger.error(f"Circuit Breaker '{self.name}' is OPEN. Fast-failing execution.")
                raise CircuitBreakerOpenException(f"Circuit Breaker '{self.name}' is currently OPEN. Call blocked.")

        # 2. Execution block
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            # Success logic
            if self.state == "HALF-OPEN":
                logger.info(f"Circuit Breaker '{self.name}' successfully recovered. Transitioning to CLOSED.")
                self.state = "CLOSED"
                self.failure_count = 0
            return result

        except Exception as e:
            # Failure logic
            self.failure_count += 1
            self.last_failure_time = time.time()
            logger.error(
                f"Circuit Breaker '{self.name}' caught failure {self.failure_count}/{self.failure_threshold}: {e}"
            )

            if self.state in ("CLOSED", "HALF-OPEN") and self.failure_count >= self.failure_threshold:
                logger.error(f"Circuit Breaker '{self.name}' tripped! Transitioning to OPEN state.")
                self.state = "OPEN"

            raise e


# Initialize global circuit breakers for LLM service and external search tool APIs
llm_breaker = AsyncCircuitBreaker("LLM_Service")
search_tool_breaker = AsyncCircuitBreaker("Search_APIs")
