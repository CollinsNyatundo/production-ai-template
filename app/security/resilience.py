import asyncio
import logging
import time
from typing import Awaitable, Callable, ParamSpec, TypeVar

from app.config import settings

logger = logging.getLogger("app.security.resilience")

P = ParamSpec("P")
T = TypeVar("T")


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
        # Guards state transitions only (not the wrapped call itself) so concurrent
        # traffic in CLOSED state is never serialized. Also tracks whether a single
        # HALF-OPEN probe is already in flight, so a burst of concurrent callers
        # during recovery doesn't all rush the downstream service at once - only
        # one probe call is let through; the rest fail fast until it resolves.
        self._lock = asyncio.Lock()
        self._half_open_probe_in_flight = False
        logger.info(
            f"Circuit Breaker '{name}' initialized (threshold={failure_threshold}, timeout={recovery_timeout}s)"
        )

    async def call(self, func: Callable[P, Awaitable[T]], *args: P.args, **kwargs: P.kwargs) -> T:
        async with self._lock:
            current_time = time.time()

            if self.state == "OPEN":
                if current_time - self.last_failure_time >= self.recovery_timeout:
                    logger.warning(
                        f"Circuit Breaker '{self.name}' transitioning from OPEN to HALF-OPEN (recovery timeout expired)"
                    )
                    self.state = "HALF-OPEN"
                    self._half_open_probe_in_flight = True
                else:
                    logger.error(f"Circuit Breaker '{self.name}' is OPEN. Fast-failing execution.")
                    raise CircuitBreakerOpenException(f"Circuit Breaker '{self.name}' is currently OPEN. Call blocked.")
            elif self.state == "HALF-OPEN":
                if self._half_open_probe_in_flight:
                    logger.warning(
                        f"Circuit Breaker '{self.name}' is HALF-OPEN with a probe already in flight. "
                        "Fast-failing this concurrent call rather than piling onto the recovering service."
                    )
                    raise CircuitBreakerOpenException(
                        f"Circuit Breaker '{self.name}' is HALF-OPEN; a recovery probe is already in flight."
                    )
                self._half_open_probe_in_flight = True
            # else: CLOSED - proceed without serializing

        try:
            result = await func(*args, **kwargs)

            async with self._lock:
                if self.state == "HALF-OPEN":
                    logger.info(f"Circuit Breaker '{self.name}' successfully recovered. Transitioning to CLOSED.")
                    self.state = "CLOSED"
                    self.failure_count = 0
                self._half_open_probe_in_flight = False
            return result

        except Exception as e:
            async with self._lock:
                self.failure_count += 1
                self.last_failure_time = time.time()
                logger.error(
                    f"Circuit Breaker '{self.name}' caught failure {self.failure_count}/{self.failure_threshold}: {e}"
                )
                if self.state in ("CLOSED", "HALF-OPEN") and self.failure_count >= self.failure_threshold:
                    logger.error(f"Circuit Breaker '{self.name}' tripped! Transitioning to OPEN state.")
                    self.state = "OPEN"
                self._half_open_probe_in_flight = False
            raise e


# Initialize global circuit breakers for LLM service and external search tool APIs
llm_breaker = AsyncCircuitBreaker("LLM_Service")
search_tool_breaker = AsyncCircuitBreaker("Search_APIs")
