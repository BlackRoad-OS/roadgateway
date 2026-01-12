"""Logging Middleware - Request/response logging.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from roadgateway_core.middleware.base import Middleware

logger = logging.getLogger(__name__)


@dataclass
class LoggingConfig:
    """Logging middleware configuration."""

    log_headers: bool = False
    log_body: bool = False
    log_query: bool = True
    skip_paths: list = None
    max_body_size: int = 1024


class LoggingMiddleware(Middleware):
    """Logging middleware for requests and responses."""

    def __init__(self, config: Optional[LoggingConfig] = None):
        self.config = config or LoggingConfig()

    def pre_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Log incoming request."""
        path = request.get("path", "")
        
        if self.config.skip_paths and path in self.config.skip_paths:
            return None

        request_id = str(uuid.uuid4())[:8]
        request["_request_id"] = request_id
        request["_start_time"] = time.time()

        method = request.get("method", "?")
        log_parts = [f"[{request_id}] --> {method} {path}"]

        if self.config.log_query:
            query = request.get("query", {})
            if query:
                log_parts.append(f"query={query}")

        if self.config.log_headers:
            headers = request.get("headers", {})
            log_parts.append(f"headers={headers}")

        logger.info(" ".join(log_parts))
        return request

    def post_request(
        self,
        request: Dict[str, Any],
        response: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Log outgoing response."""
        request_id = request.get("_request_id", "?")
        start_time = request.get("_start_time", time.time())
        
        duration_ms = (time.time() - start_time) * 1000
        status = response.get("status", 0)
        
        logger.info(f"[{request_id}] <-- {status} ({duration_ms:.2f}ms)")
        
        return None


class AccessLogMiddleware(Middleware):
    """Apache/Nginx style access logging."""

    def __init__(self, format_string: Optional[str] = None):
        # Combined log format by default
        self.format = format_string or (
            '{remote_addr} - {remote_user} [{time}] '
            '"{method} {path} {protocol}" {status} {body_bytes} '
            '"{referer}" "{user_agent}"'
        )

    def pre_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Record request start time."""
        request["_access_start"] = time.time()
        return None

    def post_request(
        self,
        request: Dict[str, Any],
        response: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Log in access log format."""
        headers = request.get("headers", {})
        
        log_data = {
            "remote_addr": request.get("remote_addr", "-"),
            "remote_user": "-",
            "time": time.strftime("%d/%b/%Y:%H:%M:%S %z"),
            "method": request.get("method", "-"),
            "path": request.get("path", "-"),
            "protocol": request.get("protocol", "HTTP/1.1"),
            "status": response.get("status", 0),
            "body_bytes": len(response.get("body", b"")),
            "referer": headers.get("Referer", "-"),
            "user_agent": headers.get("User-Agent", "-"),
        }

        logger.info(self.format.format(**log_data))
        return None


__all__ = [
    "LoggingMiddleware",
    "AccessLogMiddleware",
    "LoggingConfig",
]
