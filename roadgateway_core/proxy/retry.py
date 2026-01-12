"""Retry Policy - Request retry strategies.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BackoffStrategy(Enum):
    """Backoff strategies for retry delays."""

    CONSTANT = auto()
    LINEAR = auto()
    EXPONENTIAL = auto()
    EXPONENTIAL_JITTER = auto()
    DECORRELATED_JITTER = auto()


@dataclass
class RetryConfig:
    """Retry policy configuration."""

    max_retries: int = 3
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL_JITTER
    initial_delay: float = 0.1
    max_delay: float = 30.0
    multiplier: float = 2.0
    jitter_factor: float = 0.5
    retryable_exceptions: Set[Type[Exception]] = field(
        default_factory=lambda: {Exception}
    )
    retryable_status_codes: Set[int] = field(
        default_factory=lambda: {429, 502, 503, 504}
    )


@dataclass
class RetryResult:
    """Result of retry operation."""

    success: bool
    value: Any = None
    error: Optional[Exception] = None
    attempts: int = 0
    total_delay: float = 0.0


class RetryPolicy:
    """Retry policy with configurable backoff.

    Features:
    - Multiple backoff strategies
    - Configurable retry conditions
    - Jitter support for distributed systems
    - Callback hooks

    Backoff Strategies:
    ┌────────────────────────────────────────────────────────────┐
    │  Constant:              [d] [d] [d] [d]                     │
    │  Linear:                [d] [2d] [3d] [4d]                  │
    │  Exponential:           [d] [2d] [4d] [8d]                  │
    │  Exp + Jitter:          [d±j] [2d±j] [4d±j]                 │
    │  Decorrelated:          [rand(d, prev*3)]                   │
    └────────────────────────────────────────────────────────────┘
    """

    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
        self._on_retry_callbacks: List[Callable[[int, float, Exception], None]] = []

    def on_retry(
        self,
        callback: Callable[[int, float, Exception], None],
    ) -> "RetryPolicy":
        """Register retry callback."""
        self._on_retry_callbacks.append(callback)
        return self

    def execute(
        self,
        func: Callable[..., T],
        *args,
        **kwargs,
    ) -> RetryResult:
        """Execute function with retry policy.

        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            RetryResult with execution details
        """
        attempts = 0
        total_delay = 0.0
        last_delay = self.config.initial_delay
        last_error: Optional[Exception] = None

        while attempts <= self.config.max_retries:
            try:
                result = func(*args, **kwargs)
                return RetryResult(
                    success=True,
                    value=result,
                    attempts=attempts + 1,
                    total_delay=total_delay,
                )
            except Exception as e:
                last_error = e
                attempts += 1

                if not self._should_retry(e, attempts):
                    break

                delay = self._calculate_delay(attempts, last_delay)
                last_delay = delay
                total_delay += delay

                # Notify callbacks
                for callback in self._on_retry_callbacks:
                    try:
                        callback(attempts, delay, e)
                    except Exception:
                        pass

                logger.debug(
                    f"Retry {attempts}/{self.config.max_retries} "
                    f"after {delay:.3f}s: {e}"
                )

                time.sleep(delay)

        return RetryResult(
            success=False,
            error=last_error,
            attempts=attempts,
            total_delay=total_delay,
        )

    async def execute_async(
        self,
        func: Callable[..., T],
        *args,
        **kwargs,
    ) -> RetryResult:
        """Execute async function with retry policy."""
        attempts = 0
        total_delay = 0.0
        last_delay = self.config.initial_delay
        last_error: Optional[Exception] = None

        while attempts <= self.config.max_retries:
            try:
                result = await func(*args, **kwargs)
                return RetryResult(
                    success=True,
                    value=result,
                    attempts=attempts + 1,
                    total_delay=total_delay,
                )
            except Exception as e:
                last_error = e
                attempts += 1

                if not self._should_retry(e, attempts):
                    break

                delay = self._calculate_delay(attempts, last_delay)
                last_delay = delay
                total_delay += delay

                for callback in self._on_retry_callbacks:
                    try:
                        callback(attempts, delay, e)
                    except Exception:
                        pass

                await asyncio.sleep(delay)

        return RetryResult(
            success=False,
            error=last_error,
            attempts=attempts,
            total_delay=total_delay,
        )

    def _should_retry(self, error: Exception, attempts: int) -> bool:
        """Check if should retry."""
        if attempts > self.config.max_retries:
            return False

        for exc_type in self.config.retryable_exceptions:
            if isinstance(error, exc_type):
                return True

        return False

    def _calculate_delay(self, attempt: int, last_delay: float) -> float:
        """Calculate delay for next retry."""
        strategy = self.config.backoff_strategy
        
        if strategy == BackoffStrategy.CONSTANT:
            delay = self.config.initial_delay
            
        elif strategy == BackoffStrategy.LINEAR:
            delay = self.config.initial_delay * attempt
            
        elif strategy == BackoffStrategy.EXPONENTIAL:
            delay = self.config.initial_delay * (
                self.config.multiplier ** (attempt - 1)
            )
            
        elif strategy == BackoffStrategy.EXPONENTIAL_JITTER:
            base_delay = self.config.initial_delay * (
                self.config.multiplier ** (attempt - 1)
            )
            jitter = base_delay * self.config.jitter_factor * random.random()
            delay = base_delay + jitter
            
        elif strategy == BackoffStrategy.DECORRELATED_JITTER:
            delay = random.uniform(
                self.config.initial_delay,
                min(last_delay * 3, self.config.max_delay),
            )
        else:
            delay = self.config.initial_delay

        return min(delay, self.config.max_delay)


def retry(
    max_retries: int = 3,
    backoff: BackoffStrategy = BackoffStrategy.EXPONENTIAL_JITTER,
    initial_delay: float = 0.1,
    max_delay: float = 30.0,
    retryable_exceptions: Optional[Set[Type[Exception]]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for adding retry policy to functions.

    Usage:
        @retry(max_retries=3, backoff=BackoffStrategy.EXPONENTIAL)
        def my_function():
            ...
    """
    config = RetryConfig(
        max_retries=max_retries,
        backoff_strategy=backoff,
        initial_delay=initial_delay,
        max_delay=max_delay,
        retryable_exceptions=retryable_exceptions or {Exception},
    )
    policy = RetryPolicy(config)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args, **kwargs):
            result = policy.execute(func, *args, **kwargs)
            if result.success:
                return result.value
            raise result.error or Exception("Retry failed")
        return wrapper

    return decorator


def retry_async(
    max_retries: int = 3,
    backoff: BackoffStrategy = BackoffStrategy.EXPONENTIAL_JITTER,
    initial_delay: float = 0.1,
    max_delay: float = 30.0,
) -> Callable:
    """Decorator for adding retry policy to async functions."""
    config = RetryConfig(
        max_retries=max_retries,
        backoff_strategy=backoff,
        initial_delay=initial_delay,
        max_delay=max_delay,
    )
    policy = RetryPolicy(config)

    def decorator(func):
        async def wrapper(*args, **kwargs):
            result = await policy.execute_async(func, *args, **kwargs)
            if result.success:
                return result.value
            raise result.error or Exception("Retry failed")
        return wrapper

    return decorator


__all__ = [
    "RetryPolicy",
    "RetryConfig",
    "RetryResult",
    "BackoffStrategy",
    "retry",
    "retry_async",
]
