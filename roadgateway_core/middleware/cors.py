"""CORS Middleware - Cross-Origin Resource Sharing.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from roadgateway_core.middleware.base import Middleware

logger = logging.getLogger(__name__)


@dataclass
class CORSConfig:
    """CORS configuration."""

    allow_origins: List[str] = field(default_factory=lambda: ["*"])
    allow_methods: List[str] = field(
        default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
    )
    allow_headers: List[str] = field(
        default_factory=lambda: ["Content-Type", "Authorization", "X-Requested-With"]
    )
    expose_headers: List[str] = field(default_factory=list)
    allow_credentials: bool = False
    max_age: int = 86400


class CORSMiddleware(Middleware):
    """CORS middleware for cross-origin requests."""

    def __init__(self, config: Optional[CORSConfig] = None):
        self.config = config or CORSConfig()

    def pre_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle preflight OPTIONS requests."""
        method = request.get("method", "")
        
        if method == "OPTIONS":
            return self._preflight_response(request)
        
        return None

    def post_request(
        self,
        request: Dict[str, Any],
        response: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Add CORS headers to response."""
        headers = request.get("headers", {})
        origin = headers.get("Origin", "")

        if not origin:
            return None

        if not self._is_origin_allowed(origin):
            return None

        resp_headers = response.get("headers", {})
        
        # Add CORS headers
        if "*" in self.config.allow_origins:
            resp_headers["Access-Control-Allow-Origin"] = "*"
        else:
            resp_headers["Access-Control-Allow-Origin"] = origin

        if self.config.allow_credentials:
            resp_headers["Access-Control-Allow-Credentials"] = "true"

        if self.config.expose_headers:
            resp_headers["Access-Control-Expose-Headers"] = ", ".join(
                self.config.expose_headers
            )

        response["headers"] = resp_headers
        return response

    def _preflight_response(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Generate preflight response."""
        headers = request.get("headers", {})
        origin = headers.get("Origin", "")

        resp_headers = {}

        if self._is_origin_allowed(origin):
            if "*" in self.config.allow_origins:
                resp_headers["Access-Control-Allow-Origin"] = "*"
            else:
                resp_headers["Access-Control-Allow-Origin"] = origin

            resp_headers["Access-Control-Allow-Methods"] = ", ".join(
                self.config.allow_methods
            )
            resp_headers["Access-Control-Allow-Headers"] = ", ".join(
                self.config.allow_headers
            )
            resp_headers["Access-Control-Max-Age"] = str(self.config.max_age)

            if self.config.allow_credentials:
                resp_headers["Access-Control-Allow-Credentials"] = "true"

        return {
            "status": 204,
            "headers": resp_headers,
            "body": b"",
        }

    def _is_origin_allowed(self, origin: str) -> bool:
        """Check if origin is allowed."""
        if "*" in self.config.allow_origins:
            return True
        return origin in self.config.allow_origins


__all__ = [
    "CORSMiddleware",
    "CORSConfig",
]
