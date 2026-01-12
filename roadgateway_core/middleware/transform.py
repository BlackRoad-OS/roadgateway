"""Transform Middleware - Request/response transformation.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from roadgateway_core.middleware.base import Middleware

logger = logging.getLogger(__name__)


@dataclass
class TransformRule:
    """Transformation rule."""

    type: str  # add, remove, rename, replace
    target: str  # header, body, query
    key: str
    value: Any = None
    condition: Optional[Callable[[Dict], bool]] = None


class TransformMiddleware(Middleware):
    """Transform middleware for modifying requests/responses."""

    def __init__(
        self,
        request_transforms: Optional[List[TransformRule]] = None,
        response_transforms: Optional[List[TransformRule]] = None,
    ):
        self.request_transforms = request_transforms or []
        self.response_transforms = response_transforms or []

    def pre_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Transform request."""
        for rule in self.request_transforms:
            if rule.condition and not rule.condition(request):
                continue
            request = self._apply_transform(request, rule)
        return request

    def post_request(
        self,
        request: Dict[str, Any],
        response: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Transform response."""
        for rule in self.response_transforms:
            if rule.condition and not rule.condition(response):
                continue
            response = self._apply_transform(response, rule)
        return response

    def _apply_transform(
        self,
        data: Dict[str, Any],
        rule: TransformRule,
    ) -> Dict[str, Any]:
        """Apply transformation rule."""
        target_key = "headers" if rule.target == "header" else rule.target
        target = data.get(target_key, {})

        if rule.type == "add":
            target[rule.key] = rule.value
        elif rule.type == "remove":
            target.pop(rule.key, None)
        elif rule.type == "rename":
            if rule.key in target:
                target[rule.value] = target.pop(rule.key)
        elif rule.type == "replace":
            if rule.key in target:
                target[rule.key] = rule.value

        data[target_key] = target
        return data

    def add_header(self, key: str, value: str, request: bool = True) -> "TransformMiddleware":
        """Add header to request or response."""
        rule = TransformRule(type="add", target="header", key=key, value=value)
        if request:
            self.request_transforms.append(rule)
        else:
            self.response_transforms.append(rule)
        return self

    def remove_header(self, key: str, request: bool = True) -> "TransformMiddleware":
        """Remove header from request or response."""
        rule = TransformRule(type="remove", target="header", key=key)
        if request:
            self.request_transforms.append(rule)
        else:
            self.response_transforms.append(rule)
        return self


class HeaderMiddleware(Middleware):
    """Simple header manipulation middleware."""

    def __init__(
        self,
        add_request_headers: Optional[Dict[str, str]] = None,
        add_response_headers: Optional[Dict[str, str]] = None,
        remove_request_headers: Optional[List[str]] = None,
        remove_response_headers: Optional[List[str]] = None,
    ):
        self.add_request = add_request_headers or {}
        self.add_response = add_response_headers or {}
        self.remove_request = remove_request_headers or []
        self.remove_response = remove_response_headers or []

    def pre_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add/remove request headers."""
        headers = request.get("headers", {})

        for key in self.remove_request:
            headers.pop(key, None)

        headers.update(self.add_request)
        request["headers"] = headers
        return request

    def post_request(
        self,
        request: Dict[str, Any],
        response: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Add/remove response headers."""
        headers = response.get("headers", {})

        for key in self.remove_response:
            headers.pop(key, None)

        headers.update(self.add_response)
        response["headers"] = headers
        return response


__all__ = [
    "TransformMiddleware",
    "HeaderMiddleware",
    "TransformRule",
]
