"""
Shield Technology - Circuit Breaker Resilience Engine.
Protects downstream storage and external integrations from cascading failures.
Implements the 3-state machine: CLOSED (normal), OPEN (broken), HALF-OPEN (testing).
"""

from enum import Enum
import logging
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("shield.circuit_breaker")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"        # Normal operation: requests pass through
    OPEN = "OPEN"            # Tripped: requests fail immediately to fallback
    HALF_OPEN = "HALF_OPEN"  # Testing: limited requests allowed to verify recovery


class CircuitBreakerOpenException(Exception):
    """Raised when an operation is attempted while the circuit breaker is OPEN."""
    pass


class CircuitBreaker:
    """
    Thread-safe Circuit Breaker with failure threshold, recovery timeout,
    and automatic self-healing probe mechanisms.
    """

    def __init__(
        self,
        name: str = "default_service",
        failure_threshold: int = 5,
        recovery_timeout_sec: float = 3.0,
        half_open_max_trials: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_sec = recovery_timeout_sec
        self.half_open_max_trials = half_open_max_trials

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.total_trips = 0

    def record_success(self):
        """Records a successful execution."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.half_open_max_trials:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                logger.info("[CircuitBreaker:%s] Recovered -> CLOSED", self.name)
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def record_failure(self):
        """Records an execution error and trips to OPEN if threshold reached."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.total_trips += 1
            logger.warning("[CircuitBreaker:%s] Failed during trial -> OPEN", self.name)
        elif self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.total_trips += 1
            logger.error(
                "[CircuitBreaker:%s] Failure threshold (%d) exceeded -> OPEN",
                self.name,
                self.failure_threshold,
            )

    def allow_request(self) -> bool:
        """Determines if a request should proceed or fail fast."""
        now = time.time()
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if self.last_failure_time and (now - self.last_failure_time >= self.recovery_timeout_sec):
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                logger.info("[CircuitBreaker:%s] Timeout elapsed -> Entering HALF_OPEN trial", self.name)
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            return True

        return False

    async def call_async(self, func: Callable, *args, fallback: Optional[Callable] = None, **kwargs) -> Any:
        """Executes an asynchronous operation guarded by the circuit breaker."""
        if not self.allow_request():
            if fallback:
                return await fallback(*args, **kwargs)
            raise CircuitBreakerOpenException(f"Circuit '{self.name}' is OPEN. Fast failing.")

        try:
            res = await func(*args, **kwargs)
            self.record_success()
            return res
        except Exception as exc:
            self.record_failure()
            if fallback:
                return await fallback(*args, **kwargs)
            raise exc

    def status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "total_trips": self.total_trips,
            "recovery_timeout_sec": self.recovery_timeout_sec,
        }
