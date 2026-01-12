"""Authentication - Base authentication providers.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class AuthStatus(Enum):
    """Authentication status."""

    SUCCESS = auto()
    FAILED = auto()
    EXPIRED = auto()
    INVALID = auto()
    MISSING = auto()


@dataclass
class AuthResult:
    """Result of authentication attempt."""

    status: AuthStatus
    identity: Optional[str] = None
    claims: Dict[str, Any] = field(default_factory=dict)
    expires_at: Optional[float] = None
    error: Optional[str] = None

    @property
    def is_authenticated(self) -> bool:
        """Check if authentication succeeded."""
        return self.status == AuthStatus.SUCCESS


@dataclass
class Credentials:
    """User credentials."""

    username: str
    password: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class AuthProvider(ABC):
    """Abstract authentication provider.

    Architecture:
    ┌────────────────────────────────────────────────────────────┐
    │                   Auth Provider                             │
    ├────────────────────────────────────────────────────────────┤
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
    │  │    Basic     │  │   API Key    │  │    Bearer    │     │
    │  │    Auth      │  │    Auth      │  │    Token     │     │
    │  └──────────────┘  └──────────────┘  └──────────────┘     │
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
    │  │     JWT      │  │   OAuth2     │  │    OIDC      │     │
    │  │    Auth      │  │    Auth      │  │    Auth      │     │
    │  └──────────────┘  └──────────────┘  └──────────────┘     │
    └────────────────────────────────────────────────────────────┘
    """

    @abstractmethod
    def authenticate(self, request: Dict[str, Any]) -> AuthResult:
        """Authenticate a request.

        Args:
            request: Request data with headers

        Returns:
            AuthResult with authentication status
        """
        pass

    @abstractmethod
    def get_credentials(self, request: Dict[str, Any]) -> Optional[str]:
        """Extract credentials from request."""
        pass


class BasicAuth(AuthProvider):
    """HTTP Basic Authentication.

    Validates username:password from Authorization header.
    """

    def __init__(
        self,
        credentials: Optional[Dict[str, str]] = None,
        validator: Optional[Callable[[str, str], bool]] = None,
    ):
        self._credentials = credentials or {}
        self._validator = validator

    def add_user(self, username: str, password: str) -> "BasicAuth":
        """Add user credentials."""
        # Store hashed password
        self._credentials[username] = self._hash_password(password)
        return self

    def authenticate(self, request: Dict[str, Any]) -> AuthResult:
        """Authenticate using Basic auth."""
        creds = self.get_credentials(request)
        
        if not creds:
            return AuthResult(
                status=AuthStatus.MISSING,
                error="No credentials provided",
            )

        try:
            decoded = base64.b64decode(creds).decode()
            username, password = decoded.split(":", 1)
        except Exception:
            return AuthResult(
                status=AuthStatus.INVALID,
                error="Invalid Basic auth format",
            )

        # Validate credentials
        if self._validator:
            if self._validator(username, password):
                return AuthResult(
                    status=AuthStatus.SUCCESS,
                    identity=username,
                )
        elif username in self._credentials:
            if self._verify_password(password, self._credentials[username]):
                return AuthResult(
                    status=AuthStatus.SUCCESS,
                    identity=username,
                )

        return AuthResult(
            status=AuthStatus.FAILED,
            error="Invalid credentials",
        )

    def get_credentials(self, request: Dict[str, Any]) -> Optional[str]:
        """Extract Basic auth credentials."""
        headers = request.get("headers", {})
        auth_header = headers.get("Authorization", "")

        if auth_header.startswith("Basic "):
            return auth_header[6:]
        return None

    def _hash_password(self, password: str) -> str:
        """Hash password for storage."""
        salt = secrets.token_hex(16)
        hash_val = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            salt.encode(),
            100000,
        )
        return f"{salt}:{hash_val.hex()}"

    def _verify_password(self, password: str, stored: str) -> bool:
        """Verify password against stored hash."""
        try:
            salt, hash_val = stored.split(":")
            computed = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode(),
                salt.encode(),
                100000,
            )
            return hmac.compare_digest(computed.hex(), hash_val)
        except Exception:
            return False


class APIKeyAuth(AuthProvider):
    """API Key Authentication.

    Validates API keys from header, query, or cookie.
    """

    def __init__(
        self,
        keys: Optional[Dict[str, str]] = None,
        header_name: str = "X-API-Key",
        query_param: str = "api_key",
        validator: Optional[Callable[[str], Optional[str]]] = None,
    ):
        self._keys = keys or {}  # key -> identity mapping
        self._header_name = header_name
        self._query_param = query_param
        self._validator = validator

    def add_key(self, key: str, identity: str) -> "APIKeyAuth":
        """Add an API key."""
        self._keys[key] = identity
        return self

    def generate_key(self, identity: str) -> str:
        """Generate a new API key."""
        key = secrets.token_urlsafe(32)
        self._keys[key] = identity
        return key

    def revoke_key(self, key: str) -> bool:
        """Revoke an API key."""
        if key in self._keys:
            del self._keys[key]
            return True
        return False

    def authenticate(self, request: Dict[str, Any]) -> AuthResult:
        """Authenticate using API key."""
        key = self.get_credentials(request)

        if not key:
            return AuthResult(
                status=AuthStatus.MISSING,
                error="No API key provided",
            )

        # Custom validator
        if self._validator:
            identity = self._validator(key)
            if identity:
                return AuthResult(
                    status=AuthStatus.SUCCESS,
                    identity=identity,
                )
        # Built-in validation
        elif key in self._keys:
            return AuthResult(
                status=AuthStatus.SUCCESS,
                identity=self._keys[key],
            )

        return AuthResult(
            status=AuthStatus.FAILED,
            error="Invalid API key",
        )

    def get_credentials(self, request: Dict[str, Any]) -> Optional[str]:
        """Extract API key from request."""
        headers = request.get("headers", {})
        query = request.get("query", {})

        # Check header first
        if self._header_name in headers:
            return headers[self._header_name]

        # Then query parameter
        if self._query_param in query:
            return query[self._query_param]

        return None


class BearerTokenAuth(AuthProvider):
    """Bearer Token Authentication.

    Validates tokens from Authorization header.
    """

    def __init__(
        self,
        tokens: Optional[Dict[str, Dict[str, Any]]] = None,
        validator: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
    ):
        self._tokens = tokens or {}  # token -> {identity, claims, expires_at}
        self._validator = validator

    def add_token(
        self,
        token: str,
        identity: str,
        claims: Optional[Dict[str, Any]] = None,
        expires_at: Optional[float] = None,
    ) -> "BearerTokenAuth":
        """Add a bearer token."""
        self._tokens[token] = {
            "identity": identity,
            "claims": claims or {},
            "expires_at": expires_at,
        }
        return self

    def generate_token(
        self,
        identity: str,
        claims: Optional[Dict[str, Any]] = None,
        ttl: int = 3600,
    ) -> str:
        """Generate a new bearer token."""
        token = secrets.token_urlsafe(32)
        self._tokens[token] = {
            "identity": identity,
            "claims": claims or {},
            "expires_at": time.time() + ttl,
        }
        return token

    def revoke_token(self, token: str) -> bool:
        """Revoke a bearer token."""
        if token in self._tokens:
            del self._tokens[token]
            return True
        return False

    def authenticate(self, request: Dict[str, Any]) -> AuthResult:
        """Authenticate using bearer token."""
        token = self.get_credentials(request)

        if not token:
            return AuthResult(
                status=AuthStatus.MISSING,
                error="No bearer token provided",
            )

        # Custom validator
        if self._validator:
            data = self._validator(token)
            if data:
                return AuthResult(
                    status=AuthStatus.SUCCESS,
                    identity=data.get("identity"),
                    claims=data.get("claims", {}),
                    expires_at=data.get("expires_at"),
                )
        # Built-in validation
        elif token in self._tokens:
            data = self._tokens[token]
            
            # Check expiration
            if data.get("expires_at"):
                if time.time() > data["expires_at"]:
                    return AuthResult(
                        status=AuthStatus.EXPIRED,
                        error="Token expired",
                    )

            return AuthResult(
                status=AuthStatus.SUCCESS,
                identity=data["identity"],
                claims=data.get("claims", {}),
                expires_at=data.get("expires_at"),
            )

        return AuthResult(
            status=AuthStatus.FAILED,
            error="Invalid token",
        )

    def get_credentials(self, request: Dict[str, Any]) -> Optional[str]:
        """Extract bearer token from request."""
        headers = request.get("headers", {})
        auth_header = headers.get("Authorization", "")

        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        return None


class CompositeAuth(AuthProvider):
    """Composite authentication with multiple providers.

    Tries providers in order until one succeeds.
    """

    def __init__(self, providers: Optional[List[AuthProvider]] = None):
        self._providers = providers or []

    def add_provider(self, provider: AuthProvider) -> "CompositeAuth":
        """Add an authentication provider."""
        self._providers.append(provider)
        return self

    def authenticate(self, request: Dict[str, Any]) -> AuthResult:
        """Authenticate using any provider."""
        for provider in self._providers:
            result = provider.authenticate(request)
            if result.is_authenticated:
                return result

        return AuthResult(
            status=AuthStatus.FAILED,
            error="No provider authenticated the request",
        )

    def get_credentials(self, request: Dict[str, Any]) -> Optional[str]:
        """Get credentials from first provider that has them."""
        for provider in self._providers:
            creds = provider.get_credentials(request)
            if creds:
                return creds
        return None


__all__ = [
    "AuthProvider",
    "AuthResult",
    "AuthStatus",
    "Credentials",
    "BasicAuth",
    "APIKeyAuth",
    "BearerTokenAuth",
    "CompositeAuth",
]
