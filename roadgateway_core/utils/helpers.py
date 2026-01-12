"""Helper utilities.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def parse_url(url: str) -> Dict[str, Any]:
    """Parse URL into components."""
    parsed = urlparse(url)
    
    return {
        "scheme": parsed.scheme,
        "host": parsed.hostname or "",
        "port": parsed.port,
        "path": parsed.path,
        "query": parse_qs(parsed.query),
        "fragment": parsed.fragment,
        "username": parsed.username,
        "password": parsed.password,
    }


def build_url(
    scheme: str = "http",
    host: str = "localhost",
    port: Optional[int] = None,
    path: str = "/",
    query: Optional[Dict[str, Any]] = None,
    fragment: str = "",
) -> str:
    """Build URL from components."""
    netloc = host
    if port:
        netloc = f"{host}:{port}"

    query_string = ""
    if query:
        query_string = urlencode(query, doseq=True)

    return urlunparse((scheme, netloc, path, "", query_string, fragment))


def merge_headers(
    *headers_list: Dict[str, str],
    case_insensitive: bool = True,
) -> Dict[str, str]:
    """Merge multiple header dictionaries."""
    result = {}
    
    for headers in headers_list:
        for key, value in headers.items():
            if case_insensitive:
                # Find existing key with same lowercase
                existing_key = None
                for k in result:
                    if k.lower() == key.lower():
                        existing_key = k
                        break
                
                if existing_key:
                    del result[existing_key]
            
            result[key] = value

    return result


def normalize_path(path: str) -> str:
    """Normalize URL path."""
    if not path:
        return "/"
    
    # Remove double slashes
    while "//" in path:
        path = path.replace("//", "/")
    
    # Ensure starts with /
    if not path.startswith("/"):
        path = "/" + path
    
    # Remove trailing slash (except for root)
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    
    return path


def extract_client_ip(
    request: Dict[str, Any],
    trusted_proxies: Optional[List[str]] = None,
) -> str:
    """Extract real client IP from request."""
    headers = request.get("headers", {})
    
    # Check X-Forwarded-For
    xff = headers.get("X-Forwarded-For", "")
    if xff:
        # Get first IP (client)
        ips = [ip.strip() for ip in xff.split(",")]
        if ips:
            return ips[0]
    
    # Check X-Real-IP
    real_ip = headers.get("X-Real-IP", "")
    if real_ip:
        return real_ip
    
    # Fall back to connection IP
    return request.get("remote_addr", "")


def parse_content_type(content_type: str) -> Tuple[str, Dict[str, str]]:
    """Parse Content-Type header."""
    parts = content_type.split(";")
    media_type = parts[0].strip().lower()
    
    params = {}
    for part in parts[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            params[key.strip().lower()] = value.strip().strip('"')
    
    return media_type, params


def is_websocket_request(request: Dict[str, Any]) -> bool:
    """Check if request is a WebSocket upgrade."""
    headers = request.get("headers", {})
    
    upgrade = headers.get("Upgrade", "").lower()
    connection = headers.get("Connection", "").lower()
    
    return upgrade == "websocket" and "upgrade" in connection


__all__ = [
    "parse_url",
    "build_url",
    "merge_headers",
    "normalize_path",
    "extract_client_ip",
    "parse_content_type",
    "is_websocket_request",
]
