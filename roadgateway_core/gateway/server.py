"""Gateway Server - Core API gateway server.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import ssl
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from roadgateway_core.gateway.request import Request, Response

logger = logging.getLogger(__name__)


@dataclass
class GatewayConfig:
    """Gateway configuration."""

    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 4
    backlog: int = 1024
    timeout: float = 30.0
    ssl_enabled: bool = False
    ssl_cert: str = ""
    ssl_key: str = ""
    max_request_size: int = 10 * 1024 * 1024  # 10MB
    keepalive_timeout: float = 65.0


@dataclass
class Route:
    """Gateway route definition."""

    pattern: str
    targets: List[str]
    methods: List[str] = field(default_factory=lambda: ["*"])
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class Gateway:
    """API Gateway Server.

    Features:
    - Request routing
    - Middleware pipeline
    - Load balancing
    - Health monitoring

    Usage:
        gateway = Gateway()
        gateway.route("/api/*", targets=["backend:8080"])
        gateway.use(LoggingMiddleware())
        gateway.run()
    """

    def __init__(self, config: Optional[GatewayConfig] = None):
        self.config = config or GatewayConfig()
        self._routes: List[Route] = []
        self._middleware: List[Any] = []
        self._running = False
        self._server: Optional[socket.socket] = None
        self._lock = threading.RLock()

    def route(
        self,
        pattern: str,
        targets: List[str],
        methods: Optional[List[str]] = None,
        priority: int = 0,
        **kwargs,
    ) -> "Gateway":
        """Add a route.

        Args:
            pattern: URL pattern (e.g., "/api/*", "/users/:id")
            targets: Backend targets
            methods: HTTP methods (default: all)
            priority: Route priority (higher = first)
        """
        route = Route(
            pattern=pattern,
            targets=targets,
            methods=methods or ["*"],
            priority=priority,
            metadata=kwargs,
        )
        
        with self._lock:
            self._routes.append(route)
            self._routes.sort(key=lambda r: r.priority, reverse=True)

        return self

    def use(self, middleware: Any) -> "Gateway":
        """Add middleware to the pipeline.

        Args:
            middleware: Middleware instance
        """
        with self._lock:
            self._middleware.append(middleware)
        return self

    async def handle_request(self, request: Request) -> Response:
        """Handle incoming request through middleware and routing.

        Args:
            request: Incoming request

        Returns:
            Response from backend or middleware
        """
        # Run pre-request middleware
        for mw in self._middleware:
            if hasattr(mw, "pre_request"):
                result = await self._call_middleware(mw.pre_request, request)
                if isinstance(result, Response):
                    return result
                if result is not None:
                    request = result

        # Find matching route
        route = self._match_route(request)
        if not route:
            return Response(status=404, body=b"Not Found")

        # Select backend and forward request
        target = self._select_target(route, request)
        if not target:
            return Response(status=502, body=b"No backend available")

        # Forward to backend (simplified)
        response = await self._forward_request(request, target)

        # Run post-request middleware
        for mw in reversed(self._middleware):
            if hasattr(mw, "post_request"):
                result = await self._call_middleware(mw.post_request, request, response)
                if result is not None:
                    response = result

        return response

    def _match_route(self, request: Request) -> Optional[Route]:
        """Match request to route."""
        for route in self._routes:
            if self._pattern_matches(route.pattern, request.path):
                if route.methods == ["*"] or request.method in route.methods:
                    return route
        return None

    def _pattern_matches(self, pattern: str, path: str) -> bool:
        """Check if path matches pattern."""
        if pattern.endswith("*"):
            return path.startswith(pattern[:-1])
        if pattern.endswith("/*"):
            prefix = pattern[:-2]
            return path == prefix or path.startswith(prefix + "/")
        return pattern == path

    def _select_target(self, route: Route, request: Request) -> Optional[str]:
        """Select a target backend."""
        if not route.targets:
            return None
        # Simple round-robin for now
        import random
        return random.choice(route.targets)

    async def _forward_request(
        self,
        request: Request,
        target: str,
    ) -> Response:
        """Forward request to backend."""
        # Simplified implementation
        return Response(
            status=200,
            body=b"OK",
            headers={"X-Backend": target},
        )

    async def _call_middleware(
        self,
        method: Callable,
        *args,
    ) -> Any:
        """Call middleware method (sync or async)."""
        if asyncio.iscoroutinefunction(method):
            return await method(*args)
        return method(*args)

    def run(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        """Start the gateway server.

        Args:
            host: Override host
            port: Override port
        """
        host = host or self.config.host
        port = port or self.config.port

        logger.info(f"Starting gateway on {host}:{port}")

        self._running = True
        # Server implementation would go here
        # Using asyncio.run() for the event loop

    def stop(self) -> None:
        """Stop the gateway server."""
        self._running = False
        if self._server:
            self._server.close()

    def get_routes(self) -> List[Route]:
        """Get all registered routes."""
        return self._routes.copy()

    def get_stats(self) -> Dict[str, Any]:
        """Get gateway statistics."""
        return {
            "routes": len(self._routes),
            "middleware": len(self._middleware),
            "running": self._running,
        }


__all__ = [
    "Gateway",
    "GatewayConfig",
    "Route",
]
