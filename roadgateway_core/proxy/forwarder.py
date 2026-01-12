"""Proxy Forwarder - Request forwarding to backends.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import ssl
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ForwardStrategy(Enum):
    """Request forwarding strategies."""

    PASS_THROUGH = auto()  # Forward as-is
    REWRITE = auto()       # Rewrite URL/headers
    AGGREGATE = auto()     # Aggregate multiple backends
    MIRROR = auto()        # Mirror to multiple backends


@dataclass
class ProxyConfig:
    """Proxy configuration."""

    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    write_timeout: float = 30.0
    max_retries: int = 3
    retry_on_status: List[int] = field(default_factory=lambda: [502, 503, 504])
    buffer_size: int = 65536
    preserve_host: bool = True
    follow_redirects: bool = False
    max_redirects: int = 5
    ssl_verify: bool = True
    add_forwarded_headers: bool = True
    strip_hop_headers: bool = True


@dataclass
class ProxyResult:
    """Result of proxy operation."""

    success: bool
    status_code: int = 0
    headers: Dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    latency_ms: float = 0.0
    backend_address: str = ""
    error: Optional[str] = None
    retries: int = 0


# Headers that should not be forwarded
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class Proxy:
    """HTTP Proxy for forwarding requests to backends.

    Features:
    - Connection pooling
    - Request/response transformation
    - Header manipulation
    - SSL/TLS support
    - Streaming support

    Architecture:
    ┌────────────────────────────────────────────────────────────┐
    │                         Proxy                               │
    ├────────────────────────────────────────────────────────────┤
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
    │  │   Request    │  │  Connection  │  │   Response   │     │
    │  │ Transformer  │  │    Pool      │  │ Transformer  │     │
    │  │              │  │              │  │              │     │
    │  │ - Headers    │  │ - Keep-alive │  │ - Headers    │     │
    │  │ - URL        │  │ - SSL/TLS    │  │ - Body       │     │
    │  │ - Body       │  │ - Timeouts   │  │ - Streaming  │     │
    │  └──────────────┘  └──────────────┘  └──────────────┘     │
    └────────────────────────────────────────────────────────────┘
    """

    def __init__(self, config: Optional[ProxyConfig] = None):
        self.config = config or ProxyConfig()
        self._connections: Dict[str, socket.socket] = {}

    async def forward(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[bytes] = None,
        client_ip: Optional[str] = None,
    ) -> ProxyResult:
        """Forward request to backend.

        Args:
            method: HTTP method
            url: Target URL
            headers: Request headers
            body: Request body
            client_ip: Original client IP

        Returns:
            ProxyResult with response data
        """
        start_time = time.perf_counter()
        headers = headers or {}
        retries = 0

        # Parse target URL
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        # Prepare headers
        forward_headers = self._prepare_headers(headers, host, client_ip)

        # Try with retries
        last_error: Optional[str] = None
        
        while retries <= self.config.max_retries:
            try:
                result = await self._do_forward(
                    method=method,
                    host=host,
                    port=port,
                    path=path,
                    headers=forward_headers,
                    body=body,
                    secure=parsed.scheme == "https",
                )

                result.latency_ms = (time.perf_counter() - start_time) * 1000
                result.backend_address = f"{host}:{port}"
                result.retries = retries

                # Check if we should retry
                if result.status_code in self.config.retry_on_status:
                    retries += 1
                    if retries <= self.config.max_retries:
                        await asyncio.sleep(0.1 * retries)
                        continue

                return result

            except Exception as e:
                last_error = str(e)
                retries += 1
                if retries <= self.config.max_retries:
                    await asyncio.sleep(0.1 * retries)

        return ProxyResult(
            success=False,
            latency_ms=(time.perf_counter() - start_time) * 1000,
            backend_address=f"{host}:{port}",
            error=last_error or "Max retries exceeded",
            retries=retries,
        )

    async def _do_forward(
        self,
        method: str,
        host: str,
        port: int,
        path: str,
        headers: Dict[str, str],
        body: Optional[bytes],
        secure: bool,
    ) -> ProxyResult:
        """Execute the actual forward request."""
        try:
            # Create socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.config.connect_timeout)

            if secure:
                context = ssl.create_default_context()
                if not self.config.ssl_verify:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                sock = context.wrap_socket(sock, server_hostname=host)

            sock.connect((host, port))
            sock.settimeout(self.config.read_timeout)

            # Build HTTP request
            request_line = f"{method} {path} HTTP/1.1\r\n"
            header_lines = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
            
            if body:
                header_lines += f"Content-Length: {len(body)}\r\n"

            request = f"{request_line}{header_lines}\r\n".encode()
            
            if body:
                request += body

            # Send request
            sock.sendall(request)

            # Read response
            response_data = b""
            while True:
                chunk = sock.recv(self.config.buffer_size)
                if not chunk:
                    break
                response_data += chunk
                
                # Check if we have complete headers
                if b"\r\n\r\n" in response_data:
                    header_end = response_data.index(b"\r\n\r\n")
                    headers_raw = response_data[:header_end].decode()
                    
                    # Check for Content-Length
                    content_length = 0
                    for line in headers_raw.split("\r\n"):
                        if line.lower().startswith("content-length:"):
                            content_length = int(line.split(":")[1].strip())
                            break
                    
                    body_start = header_end + 4
                    body_received = len(response_data) - body_start
                    
                    if body_received >= content_length:
                        break

            sock.close()

            # Parse response
            return self._parse_response(response_data)

        except socket.timeout:
            return ProxyResult(
                success=False,
                error="Connection timeout",
            )
        except Exception as e:
            return ProxyResult(
                success=False,
                error=str(e),
            )

    def _prepare_headers(
        self,
        headers: Dict[str, str],
        host: str,
        client_ip: Optional[str],
    ) -> Dict[str, str]:
        """Prepare headers for forwarding."""
        forward_headers = {}

        for key, value in headers.items():
            # Strip hop-by-hop headers
            if self.config.strip_hop_headers:
                if key.lower() in HOP_BY_HOP_HEADERS:
                    continue

            forward_headers[key] = value

        # Set Host header
        if not self.config.preserve_host or "Host" not in forward_headers:
            forward_headers["Host"] = host

        # Add forwarded headers
        if self.config.add_forwarded_headers and client_ip:
            existing_xff = forward_headers.get("X-Forwarded-For", "")
            if existing_xff:
                forward_headers["X-Forwarded-For"] = f"{existing_xff}, {client_ip}"
            else:
                forward_headers["X-Forwarded-For"] = client_ip

            forward_headers["X-Real-IP"] = client_ip

        # Connection header
        forward_headers["Connection"] = "close"

        return forward_headers

    def _parse_response(self, data: bytes) -> ProxyResult:
        """Parse HTTP response."""
        try:
            # Split headers and body
            if b"\r\n\r\n" not in data:
                return ProxyResult(
                    success=False,
                    error="Invalid response: no header/body separator",
                )

            header_end = data.index(b"\r\n\r\n")
            headers_raw = data[:header_end].decode()
            body = data[header_end + 4:]

            # Parse status line
            lines = headers_raw.split("\r\n")
            status_line = lines[0]
            parts = status_line.split(" ", 2)
            
            if len(parts) < 2:
                return ProxyResult(
                    success=False,
                    error="Invalid status line",
                )

            status_code = int(parts[1])

            # Parse headers
            headers = {}
            for line in lines[1:]:
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.strip()] = value.strip()

            return ProxyResult(
                success=True,
                status_code=status_code,
                headers=headers,
                body=body,
            )

        except Exception as e:
            return ProxyResult(
                success=False,
                error=f"Response parse error: {e}",
            )


class StreamingProxy(Proxy):
    """Streaming proxy for large responses."""

    async def forward_streaming(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[bytes] = None,
    ):
        """Forward request and yield response chunks."""
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path = parsed.path or "/"
        secure = parsed.scheme == "https"

        forward_headers = self._prepare_headers(headers or {}, host, None)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.config.connect_timeout)

        if secure:
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host)

        sock.connect((host, port))
        sock.settimeout(self.config.read_timeout)

        # Send request
        request_line = f"{method} {path} HTTP/1.1\r\n"
        header_lines = "".join(f"{k}: {v}\r\n" for k, v in forward_headers.items())
        request = f"{request_line}{header_lines}\r\n".encode()
        
        if body:
            request += body

        sock.sendall(request)

        # Stream response
        headers_received = False
        buffer = b""

        while True:
            chunk = sock.recv(self.config.buffer_size)
            if not chunk:
                break

            if not headers_received:
                buffer += chunk
                if b"\r\n\r\n" in buffer:
                    header_end = buffer.index(b"\r\n\r\n")
                    yield {"type": "headers", "data": buffer[:header_end]}
                    yield {"type": "body", "data": buffer[header_end + 4:]}
                    headers_received = True
            else:
                yield {"type": "body", "data": chunk}

        sock.close()


__all__ = [
    "Proxy",
    "StreamingProxy",
    "ProxyConfig",
    "ProxyResult",
    "ForwardStrategy",
    "HOP_BY_HOP_HEADERS",
]
