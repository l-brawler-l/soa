"""Circuit Breaker pattern implementation."""
import logging
import time
from enum import Enum
from typing import Callable, Any
from functools import wraps
import threading

from .config import settings

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open."""
    pass


class CircuitBreaker:
    """
    Circuit Breaker implementation.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Failures exceeded threshold, requests fail immediately
    - HALF_OPEN: Testing if service recovered, allow limited requests
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: int = 30,
        half_open_max_calls: int = 1
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            timeout_seconds: Time to wait before transitioning to HALF_OPEN
            half_open_max_calls: Max calls allowed in HALF_OPEN state
        """
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.half_open_max_calls = half_open_max_calls

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.half_open_calls = 0

        self._lock = threading.Lock()

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return False
        return time.time() - self.last_failure_time >= self.timeout_seconds

    def _transition_to_open(self):
        """Transition to OPEN state."""
        self.state = CircuitState.OPEN
        self.last_failure_time = time.time()
        logger.warning(
            f"Circuit breaker OPEN: {self.failure_count} failures exceeded threshold {self.failure_threshold}"
        )

    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state."""
        self.state = CircuitState.HALF_OPEN
        self.half_open_calls = 0
        logger.info("Circuit breaker HALF_OPEN: Testing service recovery")

    def _transition_to_closed(self):
        """Transition to CLOSED state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.half_open_calls = 0
        logger.info("Circuit breaker CLOSED: Service recovered")

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerError: If circuit is open
        """
        with self._lock:
            # Check if we should transition from OPEN to HALF_OPEN
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._transition_to_half_open()
                else:
                    raise CircuitBreakerError(
                        f"Circuit breaker is OPEN. Service unavailable. "
                        f"Retry after {self.timeout_seconds}s"
                    )

            # In HALF_OPEN, limit number of calls
            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_calls >= self.half_open_max_calls:
                    raise CircuitBreakerError(
                        "Circuit breaker is HALF_OPEN. Max test calls reached."
                    )
                self.half_open_calls += 1

        # Execute the function
        try:
            result = func(*args, **kwargs)

            # Success - handle state transitions
            with self._lock:
                if self.state == CircuitState.HALF_OPEN:
                    self._transition_to_closed()
                elif self.state == CircuitState.CLOSED:
                    # Reset failure count on success
                    self.failure_count = 0

            return result

        except Exception as e:
            # Failure - handle state transitions
            with self._lock:
                self.failure_count += 1
                self.last_failure_time = time.time()

                if self.state == CircuitState.HALF_OPEN:
                    # Failed in HALF_OPEN, go back to OPEN
                    self._transition_to_open()
                elif self.state == CircuitState.CLOSED:
                    # Check if we should open the circuit
                    if self.failure_count >= self.failure_threshold:
                        self._transition_to_open()

            raise

    def get_state(self) -> CircuitState:
        """Get current circuit breaker state."""
        return self.state


# Global circuit breaker instance
circuit_breaker = CircuitBreaker(
    failure_threshold=settings.circuit_breaker_failure_threshold,
    timeout_seconds=settings.circuit_breaker_timeout_seconds,
    half_open_max_calls=settings.circuit_breaker_half_open_max_calls
)


def with_circuit_breaker(func: Callable) -> Callable:
    """
    Decorator to apply circuit breaker to a function.

    Args:
        func: Function to protect

    Returns:
        Wrapped function
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        return circuit_breaker.call(func, *args, **kwargs)

    return wrapper
