"""Router - Request routing engine.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class Route:
    """Route definition."""

    pattern: str
    handler: Optional[Callable] = None
    targets: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=lambda: ["*"])
    name: str = ""
    priority: int = 0
    middleware: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Compiled pattern
    _regex: Optional[re.Pattern] = field(default=None, repr=False)
    _param_names: List[str] = field(default_factory=list, repr=False)

    def __post_init__(self):
        """Compile pattern to regex."""
        self._compile_pattern()

    def _compile_pattern(self) -> None:
        """Compile pattern to regex with named groups."""
        self._param_names = []
        regex_pattern = self.pattern

        # Replace :param with named groups
        param_pattern = re.compile(r":(\w+)")
        for match in param_pattern.finditer(self.pattern):
            param_name = match.group(1)
            self._param_names.append(param_name)
            regex_pattern = regex_pattern.replace(
                f":{param_name}",
                f"(?P<{param_name}>[^/]+)"
            )

        # Handle wildcards
        regex_pattern = regex_pattern.replace("/*", "/.*")
        regex_pattern = regex_pattern.replace("*", ".*")

        self._regex = re.compile(f"^{regex_pattern}$")

    def matches(self, path: str, method: str = "GET") -> Optional[Dict[str, str]]:
        """Check if route matches path and method.

        Returns:
            Dict of path parameters if match, None otherwise
        """
        # Check method
        if "*" not in self.methods and method not in self.methods:
            return None

        # Check pattern
        if self._regex:
            match = self._regex.match(path)
            if match:
                return match.groupdict()

        return None


class Router:
    """Request Router.

    Features:
    - Pattern-based routing
    - Path parameters (/users/:id)
    - Wildcard patterns (/api/*)
    - Method filtering
    - Route prioritization

    Usage:
        router = Router()
        router.add("/users/:id", handler=get_user, methods=["GET"])
        router.add("/api/*", targets=["backend:8080"])
        
        match = router.match("/users/123", "GET")
        if match:
            route, params = match
    """

    def __init__(self):
        self._routes: List[Route] = []
        self._lock = threading.RLock()

    def add(
        self,
        pattern: str,
        handler: Optional[Callable] = None,
        targets: Optional[List[str]] = None,
        methods: Optional[List[str]] = None,
        name: str = "",
        priority: int = 0,
        **kwargs,
    ) -> "Router":
        """Add a route.

        Args:
            pattern: URL pattern
            handler: Request handler function
            targets: Backend targets
            methods: HTTP methods
            name: Route name
            priority: Route priority
        """
        route = Route(
            pattern=pattern,
            handler=handler,
            targets=targets or [],
            methods=methods or ["*"],
            name=name,
            priority=priority,
            metadata=kwargs,
        )

        with self._lock:
            self._routes.append(route)
            self._routes.sort(key=lambda r: r.priority, reverse=True)

        return self

    def match(
        self,
        path: str,
        method: str = "GET",
    ) -> Optional[Tuple[Route, Dict[str, str]]]:
        """Match a request to a route.

        Args:
            path: Request path
            method: HTTP method

        Returns:
            Tuple of (route, params) if match, None otherwise
        """
        with self._lock:
            for route in self._routes:
                params = route.matches(path, method)
                if params is not None:
                    return route, params

        return None

    def remove(self, name: str) -> bool:
        """Remove a route by name."""
        with self._lock:
            for i, route in enumerate(self._routes):
                if route.name == name:
                    self._routes.pop(i)
                    return True
        return False

    def get_routes(self) -> List[Route]:
        """Get all routes."""
        return self._routes.copy()

    def get(self, pattern: str, **kwargs) -> "Router":
        """Add GET route."""
        return self.add(pattern, methods=["GET"], **kwargs)

    def post(self, pattern: str, **kwargs) -> "Router":
        """Add POST route."""
        return self.add(pattern, methods=["POST"], **kwargs)

    def put(self, pattern: str, **kwargs) -> "Router":
        """Add PUT route."""
        return self.add(pattern, methods=["PUT"], **kwargs)

    def delete(self, pattern: str, **kwargs) -> "Router":
        """Add DELETE route."""
        return self.add(pattern, methods=["DELETE"], **kwargs)

    def patch(self, pattern: str, **kwargs) -> "Router":
        """Add PATCH route."""
        return self.add(pattern, methods=["PATCH"], **kwargs)


__all__ = [
    "Router",
    "Route",
]
