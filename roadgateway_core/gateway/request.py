"""Request/Response - HTTP request and response objects.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class Request:
    """HTTP Request object.

    Represents an incoming HTTP request with all its components.
    """

    method: str
    path: str
    headers: Dict[str, str] = field(default_factory=dict)
    query: Dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    remote_addr: str = ""
    protocol: str = "HTTP/1.1"
    timestamp: float = field(default_factory=time.time)
    
    # Internal
    _params: Dict[str, str] = field(default_factory=dict)
    _context: Dict[str, Any] = field(default_factory=dict)

    @property
    def content_type(self) -> str:
        """Get Content-Type header."""
        return self.headers.get("Content-Type", "")

    @property
    def content_length(self) -> int:
        """Get Content-Length header."""
        try:
            return int(self.headers.get("Content-Length", 0))
        except ValueError:
            return 0

    @property
    def is_json(self) -> bool:
        """Check if request is JSON."""
        return "application/json" in self.content_type

    def json(self) -> Any:
        """Parse body as JSON."""
        return json.loads(self.body.decode())

    def text(self) -> str:
        """Get body as text."""
        return self.body.decode()

    def get_header(self, name: str, default: str = "") -> str:
        """Get header value (case-insensitive)."""
        for key, value in self.headers.items():
            if key.lower() == name.lower():
                return value
        return default

    def set_header(self, name: str, value: str) -> None:
        """Set header value."""
        self.headers[name] = value

    @classmethod
    def from_raw(cls, data: bytes) -> "Request":
        """Parse request from raw HTTP data."""
        lines = data.split(b"\r\n")
        
        # Parse request line
        request_line = lines[0].decode()
        parts = request_line.split(" ")
        method = parts[0]
        path = parts[1] if len(parts) > 1 else "/"
        protocol = parts[2] if len(parts) > 2 else "HTTP/1.1"

        # Parse query string
        query = {}
        if "?" in path:
            path, query_string = path.split("?", 1)
            for param in query_string.split("&"):
                if "=" in param:
                    key, value = param.split("=", 1)
                    query[key] = value

        # Parse headers
        headers = {}
        body_start = 0
        for i, line in enumerate(lines[1:], 1):
            if line == b"":
                body_start = i + 1
                break
            if b":" in line:
                key, value = line.decode().split(":", 1)
                headers[key.strip()] = value.strip()

        # Get body
        body = b"\r\n".join(lines[body_start:]) if body_start else b""

        return cls(
            method=method,
            path=path,
            headers=headers,
            query=query,
            body=body,
            protocol=protocol,
        )


@dataclass
class Response:
    """HTTP Response object.

    Represents an outgoing HTTP response.
    """

    status: int = 200
    body: bytes = b""
    headers: Dict[str, str] = field(default_factory=dict)
    
    # Common status messages
    STATUS_MESSAGES = {
        200: "OK",
        201: "Created",
        204: "No Content",
        301: "Moved Permanently",
        302: "Found",
        304: "Not Modified",
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        408: "Request Timeout",
        429: "Too Many Requests",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
        504: "Gateway Timeout",
    }

    @property
    def status_message(self) -> str:
        """Get status message."""
        return self.STATUS_MESSAGES.get(self.status, "Unknown")

    @property
    def is_success(self) -> bool:
        """Check if response is successful (2xx)."""
        return 200 <= self.status < 300

    @property
    def is_redirect(self) -> bool:
        """Check if response is redirect (3xx)."""
        return 300 <= self.status < 400

    @property
    def is_error(self) -> bool:
        """Check if response is error (4xx or 5xx)."""
        return self.status >= 400

    def set_header(self, name: str, value: str) -> "Response":
        """Set header value."""
        self.headers[name] = value
        return self

    def to_bytes(self) -> bytes:
        """Convert to raw HTTP response."""
        lines = [f"HTTP/1.1 {self.status} {self.status_message}"]
        
        # Add Content-Length if not set
        if "Content-Length" not in self.headers:
            self.headers["Content-Length"] = str(len(self.body))

        for key, value in self.headers.items():
            lines.append(f"{key}: {value}")

        lines.append("")
        header_bytes = "\r\n".join(lines).encode()
        
        return header_bytes + b"\r\n" + self.body

    @classmethod
    def json(
        cls,
        data: Any,
        status: int = 200,
        headers: Optional[Dict[str, str]] = None,
    ) -> "Response":
        """Create JSON response."""
        body = json.dumps(data).encode()
        resp_headers = headers or {}
        resp_headers["Content-Type"] = "application/json"
        return cls(status=status, body=body, headers=resp_headers)

    @classmethod
    def text(
        cls,
        text: str,
        status: int = 200,
        headers: Optional[Dict[str, str]] = None,
    ) -> "Response":
        """Create text response."""
        body = text.encode()
        resp_headers = headers or {}
        resp_headers["Content-Type"] = "text/plain"
        return cls(status=status, body=body, headers=resp_headers)

    @classmethod
    def html(
        cls,
        html: str,
        status: int = 200,
        headers: Optional[Dict[str, str]] = None,
    ) -> "Response":
        """Create HTML response."""
        body = html.encode()
        resp_headers = headers or {}
        resp_headers["Content-Type"] = "text/html"
        return cls(status=status, body=body, headers=resp_headers)

    @classmethod
    def redirect(
        cls,
        location: str,
        status: int = 302,
    ) -> "Response":
        """Create redirect response."""
        return cls(
            status=status,
            headers={"Location": location},
        )

    @classmethod
    def error(
        cls,
        status: int,
        message: Optional[str] = None,
    ) -> "Response":
        """Create error response."""
        msg = message or cls.STATUS_MESSAGES.get(status, "Error")
        return cls.json({"error": msg}, status=status)


__all__ = [
    "Request",
    "Response",
]
