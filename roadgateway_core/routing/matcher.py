"""Route Matcher - Pattern matching utilities.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import fnmatch
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


class PatternMatcher(ABC):
    """Abstract pattern matcher."""

    @abstractmethod
    def matches(self, pattern: str, value: str) -> bool:
        """Check if value matches pattern."""
        pass

    @abstractmethod
    def extract(self, pattern: str, value: str) -> Optional[Dict[str, str]]:
        """Extract variables from pattern match."""
        pass


class GlobMatcher(PatternMatcher):
    """Glob-style pattern matcher."""

    def matches(self, pattern: str, value: str) -> bool:
        """Match using glob patterns."""
        return fnmatch.fnmatch(value, pattern)

    def extract(self, pattern: str, value: str) -> Optional[Dict[str, str]]:
        """Glob doesn't support extraction."""
        if self.matches(pattern, value):
            return {}
        return None


class RegexMatcher(PatternMatcher):
    """Regex pattern matcher."""

    def __init__(self):
        self._cache: Dict[str, re.Pattern] = {}

    def matches(self, pattern: str, value: str) -> bool:
        """Match using regex."""
        regex = self._get_regex(pattern)
        return regex.match(value) is not None

    def extract(self, pattern: str, value: str) -> Optional[Dict[str, str]]:
        """Extract named groups from match."""
        regex = self._get_regex(pattern)
        match = regex.match(value)
        if match:
            return match.groupdict()
        return None

    def _get_regex(self, pattern: str) -> re.Pattern:
        """Get compiled regex (cached)."""
        if pattern not in self._cache:
            self._cache[pattern] = re.compile(pattern)
        return self._cache[pattern]


class PathMatcher(PatternMatcher):
    """URL path pattern matcher.

    Supports:
    - Exact matches: /users
    - Path parameters: /users/:id
    - Wildcards: /api/*
    - Optional segments: /users/:id?
    """

    def __init__(self):
        self._cache: Dict[str, Tuple[re.Pattern, List[str]]] = {}

    def matches(self, pattern: str, value: str) -> bool:
        """Check if path matches pattern."""
        return self.extract(pattern, value) is not None

    def extract(self, pattern: str, value: str) -> Optional[Dict[str, str]]:
        """Extract path parameters."""
        regex, param_names = self._compile(pattern)
        match = regex.match(value)
        
        if match:
            return match.groupdict()
        return None

    def _compile(self, pattern: str) -> Tuple[re.Pattern, List[str]]:
        """Compile pattern to regex."""
        if pattern in self._cache:
            return self._cache[pattern]

        param_names = []
        regex_parts = []
        
        for segment in pattern.split("/"):
            if not segment:
                continue
                
            if segment.startswith(":"):
                # Path parameter
                param_name = segment[1:]
                optional = param_name.endswith("?")
                if optional:
                    param_name = param_name[:-1]
                    regex_parts.append(f"(?:/(?P<{param_name}>[^/]+))?")
                else:
                    regex_parts.append(f"/(?P<{param_name}>[^/]+)")
                param_names.append(param_name)
            elif segment == "*":
                # Wildcard
                regex_parts.append("/.*")
            elif segment == "**":
                # Multi-segment wildcard
                regex_parts.append("(?:/.*)?")
            else:
                # Exact match
                regex_parts.append(f"/{re.escape(segment)}")

        regex_str = "^" + "".join(regex_parts) + "$"
        regex = re.compile(regex_str)
        
        self._cache[pattern] = (regex, param_names)
        return regex, param_names


class RouteMatcher:
    """Combined route matcher.

    Matches requests based on:
    - Path pattern
    - HTTP method
    - Headers
    - Query parameters
    """

    def __init__(self):
        self._path_matcher = PathMatcher()

    def matches(
        self,
        pattern: str,
        path: str,
        method: str = "GET",
        methods: Optional[List[str]] = None,
        headers: Optional[Dict[str, str]] = None,
        required_headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, str]]:
        """Match request against route criteria.

        Args:
            pattern: URL pattern
            path: Request path
            method: HTTP method
            methods: Allowed methods
            headers: Request headers
            required_headers: Required header values

        Returns:
            Dict of extracted parameters if match, None otherwise
        """
        # Check method
        if methods and "*" not in methods:
            if method not in methods:
                return None

        # Check path
        params = self._path_matcher.extract(pattern, path)
        if params is None:
            return None

        # Check required headers
        if required_headers and headers:
            for key, expected in required_headers.items():
                actual = headers.get(key, "")
                if expected != "*" and actual != expected:
                    return None

        return params


__all__ = [
    "PatternMatcher",
    "GlobMatcher",
    "RegexMatcher",
    "PathMatcher",
    "RouteMatcher",
]
