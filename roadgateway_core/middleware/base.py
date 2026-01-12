"""Middleware Base - Base classes for middleware.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class Middleware(ABC):
    """Abstract middleware base class.

    Middleware can process requests before routing and
    responses before sending to client.

    Pipeline:
    ┌────────────────────────────────────────────────────────────┐
    │                  Middleware Pipeline                        │
    │                                                             │
    │  Request ──▶ MW1 ──▶ MW2 ──▶ ... ──▶ Handler               │
    │                                          │                  │
    │  Response ◀── MW1 ◀── MW2 ◀── ... ◀──────┘                 │
    └────────────────────────────────────────────────────────────┘
    """

    @abstractmethod
    def pre_request(
        self,
        request: Dict[str, Any],
    ) -> Optional[Union[Dict[str, Any], Any]]:
        """Process request before routing.

        Args:
            request: Request object

        Returns:
            Modified request, Response to short-circuit, or None
        """
        pass

    @abstractmethod
    def post_request(
        self,
        request: Dict[str, Any],
        response: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Process response before sending.

        Args:
            request: Original request
            response: Response from handler

        Returns:
            Modified response or None
        """
        pass


class MiddlewareChain:
    """Chain of middleware for sequential execution."""

    def __init__(self, middleware: Optional[List[Middleware]] = None):
        self._middleware = middleware or []

    def add(self, middleware: Middleware) -> "MiddlewareChain":
        """Add middleware to chain."""
        self._middleware.append(middleware)
        return self

    def remove(self, middleware: Middleware) -> bool:
        """Remove middleware from chain."""
        try:
            self._middleware.remove(middleware)
            return True
        except ValueError:
            return False

    async def process_request(
        self,
        request: Dict[str, Any],
    ) -> tuple:
        """Process request through all middleware.

        Returns:
            Tuple of (modified_request, short_circuit_response)
        """
        current_request = request

        for mw in self._middleware:
            try:
                result = mw.pre_request(current_request)
                
                if result is None:
                    continue
                    
                if isinstance(result, dict) and "status" in result:
                    # Short-circuit response
                    return current_request, result
                    
                current_request = result
                
            except Exception as e:
                logger.error(f"Middleware pre_request error: {e}")

        return current_request, None

    async def process_response(
        self,
        request: Dict[str, Any],
        response: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Process response through all middleware (reverse order)."""
        current_response = response

        for mw in reversed(self._middleware):
            try:
                result = mw.post_request(request, current_response)
                if result is not None:
                    current_response = result
            except Exception as e:
                logger.error(f"Middleware post_request error: {e}")

        return current_response

    def __len__(self) -> int:
        return len(self._middleware)


class PassthroughMiddleware(Middleware):
    """Middleware that does nothing (for testing)."""

    def pre_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return None

    def post_request(
        self,
        request: Dict[str, Any],
        response: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return None


__all__ = [
    "Middleware",
    "MiddlewareChain",
    "PassthroughMiddleware",
]
