"""Rate Limiter - Rate limiting implementation.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from roadgateway_core.ratelimit.algorithms import Algorithm, TokenBucket

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limiter configuration."""

    requests_per_second: float = 10.0
    requests_per_minute: float = 600.0
    burst_size: int = 20
    key_prefix: str = "rl:"
    include_headers: bool = True


@dataclass
class RateLimitResult:
    """Result of rate limit check."""

    allowed: bool
    remaining: int = 0
    limit: int = 0
    reset_after: float = 0.0
    retry_after: float = 0.0


class RateLimiter:
    """Rate Limiter.

    Features:
    - Multiple algorithms (token bucket, sliding window, etc.)
    - Per-key rate limiting
    - Configurable limits
    - Response headers

    Usage:
        limiter = RateLimiter(requests_per_second=10)

        if limiter.allow("user-123"):
            # Process request
            pass
        else:
            # Return 429 Too Many Requests
            pass
    """

    def __init__(
        self,
        requests_per_second: float = 10.0,
        algorithm: Optional[Algorithm] = None,
        config: Optional[RateLimitConfig] = None,
    ):
        self.config = config or RateLimitConfig(
            requests_per_second=requests_per_second
        )
        self._algorithm = algorithm or TokenBucket(
            capacity=int(requests_per_second * 2),
            refill_rate=requests_per_second,
        )
        self._buckets: Dict[str, Algorithm] = {}
        self._lock = threading.RLock()

    def allow(self, key: str) -> bool:
        """Check if request is allowed.

        Args:
            key: Rate limit key (e.g., user ID, IP address)

        Returns:
            True if allowed, False if rate limited
        """
        return self.check(key).allowed

    def check(self, key: str) -> RateLimitResult:
        """Check rate limit and get detailed result.

        Args:
            key: Rate limit key

        Returns:
            RateLimitResult with limit details
        """
        full_key = f"{self.config.key_prefix}{key}"

        with self._lock:
            if full_key not in self._buckets:
                self._buckets[full_key] = TokenBucket(
                    capacity=int(self.config.requests_per_second * 2),
                    refill_rate=self.config.requests_per_second,
                )

            bucket = self._buckets[full_key]
            allowed = bucket.allow()

            return RateLimitResult(
                allowed=allowed,
                remaining=int(bucket.tokens) if hasattr(bucket, "tokens") else 0,
                limit=int(bucket.capacity) if hasattr(bucket, "capacity") else 0,
                reset_after=1.0 / bucket.refill_rate if hasattr(bucket, "refill_rate") else 1.0,
                retry_after=0.0 if allowed else 1.0,
            )

    def reset(self, key: str) -> None:
        """Reset rate limit for key."""
        full_key = f"{self.config.key_prefix}{key}"
        with self._lock:
            self._buckets.pop(full_key, None)

    def get_headers(self, result: RateLimitResult) -> Dict[str, str]:
        """Get rate limit response headers."""
        headers = {
            "X-RateLimit-Limit": str(result.limit),
            "X-RateLimit-Remaining": str(result.remaining),
            "X-RateLimit-Reset": str(int(time.time() + result.reset_after)),
        }

        if not result.allowed:
            headers["Retry-After"] = str(int(result.retry_after))

        return headers


class DistributedRateLimiter(RateLimiter):
    """Rate limiter with distributed backend support."""

    def __init__(
        self,
        backend: Any,  # Redis, Memcached, etc.
        requests_per_second: float = 10.0,
        config: Optional[RateLimitConfig] = None,
    ):
        super().__init__(requests_per_second, config=config)
        self._backend = backend

    def check(self, key: str) -> RateLimitResult:
        """Check rate limit using distributed backend."""
        # This would use Redis INCR + EXPIRE for distributed limiting
        # Falling back to local for now
        return super().check(key)


__all__ = [
    "RateLimiter",
    "RateLimitConfig",
    "RateLimitResult",
    "DistributedRateLimiter",
]
