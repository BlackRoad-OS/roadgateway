"""Rate Limiter Middleware - Middleware for rate limiting.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from roadgateway_core.middleware.base import Middleware
from roadgateway_core.ratelimit.limiter import RateLimiter, RateLimitResult

logger = logging.getLogger(__name__)


@dataclass
class RateLimiterMiddlewareConfig:
    """Rate limiter middleware configuration."""

    requests_per_second: float = 10.0
    requests_per_minute: float = 600.0
    key_func: Optional[Callable[[Dict], str]] = None
    skip_paths: List[str] = field(default_factory=list)
    include_headers: bool = True
    error_body: Dict[str, Any] = field(
        default_factory=lambda: {"error": "Too Many Requests"}
    )


class RateLimiterMiddleware(Middleware):
    """Middleware that enforces rate limits."""

    def __init__(
        self,
        config: Optional[RateLimiterMiddlewareConfig] = None,
        limiter: Optional[RateLimiter] = None,
    ):
        self.config = config or RateLimiterMiddlewareConfig()
        self._limiter = limiter or RateLimiter(
            requests_per_second=self.config.requests_per_second
        )

    def pre_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Check rate limit before processing."""
        path = request.get("path", "")

        # Skip configured paths
        for skip_path in self.config.skip_paths:
            if path.startswith(skip_path):
                return None

        # Get rate limit key
        key = self._get_key(request)
        result = self._limiter.check(key)

        if not result.allowed:
            response = {
                "status": 429,
                "body": self.config.error_body,
                "headers": {},
            }

            if self.config.include_headers:
                response["headers"] = self._limiter.get_headers(result)

            return response

        # Store result for response headers
        request["_rate_limit_result"] = result
        return None

    def post_request(
        self,
        request: Dict[str, Any],
        response: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Add rate limit headers to response."""
        if not self.config.include_headers:
            return None

        result = request.get("_rate_limit_result")
        if result:
            headers = response.get("headers", {})
            headers.update(self._limiter.get_headers(result))
            response["headers"] = headers

        return response

    def _get_key(self, request: Dict[str, Any]) -> str:
        """Get rate limit key from request."""
        if self.config.key_func:
            return self.config.key_func(request)

        # Default: use client IP
        return request.get("remote_addr", "unknown")


class IPRateLimiterMiddleware(RateLimiterMiddleware):
    """Rate limiter that uses client IP as key."""

    def _get_key(self, request: Dict[str, Any]) -> str:
        headers = request.get("headers", {})

        # Check X-Forwarded-For
        xff = headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()

        # Check X-Real-IP
        real_ip = headers.get("X-Real-IP", "")
        if real_ip:
            return real_ip

        return request.get("remote_addr", "unknown")


class UserRateLimiterMiddleware(RateLimiterMiddleware):
    """Rate limiter that uses user ID as key."""

    def __init__(
        self,
        user_key: str = "user_id",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._user_key = user_key

    def _get_key(self, request: Dict[str, Any]) -> str:
        # Look for user ID in request context
        user_id = request.get("_context", {}).get(self._user_key)
        if user_id:
            return f"user:{user_id}"

        # Fall back to IP
        return f"ip:{request.get('remote_addr', 'unknown')}"


__all__ = [
    "RateLimiterMiddleware",
    "RateLimiterMiddlewareConfig",
    "IPRateLimiterMiddleware",
    "UserRateLimiterMiddleware",
]
