"""OAuth2 - OAuth 2.0 authentication provider.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import urlencode

from roadgateway_core.security.auth import AuthProvider, AuthResult, AuthStatus

logger = logging.getLogger(__name__)


class OAuth2GrantType(Enum):
    """OAuth2 grant types."""

    AUTHORIZATION_CODE = "authorization_code"
    CLIENT_CREDENTIALS = "client_credentials"
    PASSWORD = "password"
    REFRESH_TOKEN = "refresh_token"
    IMPLICIT = "implicit"  # Deprecated but still used


class OAuth2ResponseType(Enum):
    """OAuth2 response types."""

    CODE = "code"
    TOKEN = "token"


@dataclass
class OAuth2Config:
    """OAuth2 configuration."""

    client_id: str = ""
    client_secret: str = ""
    authorization_endpoint: str = ""
    token_endpoint: str = ""
    redirect_uri: str = ""
    scopes: Set[str] = field(default_factory=set)
    state_length: int = 32
    token_expiry: int = 3600
    refresh_token_expiry: int = 86400 * 30


@dataclass
class OAuth2Token:
    """OAuth2 token response."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    id_token: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
        }
        if self.refresh_token:
            result["refresh_token"] = self.refresh_token
        if self.scope:
            result["scope"] = self.scope
        if self.id_token:
            result["id_token"] = self.id_token
        return result


@dataclass
class OAuth2Client:
    """OAuth2 client registration."""

    client_id: str
    client_secret: str
    redirect_uris: List[str] = field(default_factory=list)
    grant_types: Set[OAuth2GrantType] = field(default_factory=set)
    scopes: Set[str] = field(default_factory=set)
    name: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuthorizationCode:
    """Authorization code data."""

    code: str
    client_id: str
    redirect_uri: str
    scope: str
    user_id: str
    expires_at: float
    code_challenge: Optional[str] = None
    code_challenge_method: Optional[str] = None


class OAuth2Provider(AuthProvider):
    """OAuth2 Authentication Provider.

    Features:
    - Authorization Code flow
    - Client Credentials flow
    - Password grant
    - Refresh tokens
    - PKCE support

    OAuth2 Flows:
    ┌────────────────────────────────────────────────────────────────┐
    │                    Authorization Code Flow                      │
    │                                                                 │
    │  ┌──────┐    1. Auth Request    ┌──────────────┐              │
    │  │      │ ─────────────────────▶│              │              │
    │  │ User │                        │ Auth Server │              │
    │  │      │◀───────────────────── │              │              │
    │  └──────┘    2. Auth Code        └──────────────┘              │
    │      │                                  │                       │
    │      │                                  │                       │
    │      ▼                                  │                       │
    │  ┌──────┐    3. Code + Creds           │                       │
    │  │      │ ─────────────────────────────┘                       │
    │  │Client│                                                       │
    │  │      │◀───────────────────────────────                      │
    │  └──────┘    4. Access Token                                    │
    └────────────────────────────────────────────────────────────────┘
    """

    def __init__(self, config: Optional[OAuth2Config] = None):
        self.config = config or OAuth2Config()
        
        # Storage
        self._clients: Dict[str, OAuth2Client] = {}
        self._codes: Dict[str, AuthorizationCode] = {}
        self._tokens: Dict[str, Dict[str, Any]] = {}
        self._refresh_tokens: Dict[str, Dict[str, Any]] = {}

    def register_client(self, client: OAuth2Client) -> None:
        """Register an OAuth2 client."""
        self._clients[client.client_id] = client

    def authenticate(self, request: Dict[str, Any]) -> AuthResult:
        """Authenticate request using OAuth2 token."""
        token = self.get_credentials(request)

        if not token:
            return AuthResult(
                status=AuthStatus.MISSING,
                error="No access token provided",
            )

        token_data = self._tokens.get(token)
        if not token_data:
            return AuthResult(
                status=AuthStatus.INVALID,
                error="Invalid access token",
            )

        if time.time() > token_data["expires_at"]:
            return AuthResult(
                status=AuthStatus.EXPIRED,
                error="Access token expired",
            )

        return AuthResult(
            status=AuthStatus.SUCCESS,
            identity=token_data["user_id"],
            claims={
                "client_id": token_data["client_id"],
                "scope": token_data["scope"],
            },
            expires_at=token_data["expires_at"],
        )

    def get_credentials(self, request: Dict[str, Any]) -> Optional[str]:
        """Extract access token from request."""
        headers = request.get("headers", {})
        auth_header = headers.get("Authorization", "")

        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        return None

    def authorize(
        self,
        client_id: str,
        redirect_uri: str,
        scope: str,
        state: str,
        user_id: str,
        response_type: OAuth2ResponseType = OAuth2ResponseType.CODE,
        code_challenge: Optional[str] = None,
        code_challenge_method: Optional[str] = None,
    ) -> Dict[str, str]:
        """Handle authorization request."""
        client = self._clients.get(client_id)
        if not client:
            return {"error": "invalid_client"}

        if redirect_uri not in client.redirect_uris:
            return {"error": "invalid_redirect_uri"}

        if response_type == OAuth2ResponseType.CODE:
            # Generate authorization code
            code = secrets.token_urlsafe(32)
            self._codes[code] = AuthorizationCode(
                code=code,
                client_id=client_id,
                redirect_uri=redirect_uri,
                scope=scope,
                user_id=user_id,
                expires_at=time.time() + 600,  # 10 minutes
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
            )
            return {
                "redirect_uri": f"{redirect_uri}?code={code}&state={state}",
            }
        else:
            # Implicit flow (deprecated)
            token = self._generate_token(client_id, user_id, scope)
            return {
                "redirect_uri": f"{redirect_uri}#access_token={token.access_token}&state={state}",
            }

    def token(
        self,
        grant_type: OAuth2GrantType,
        client_id: str,
        client_secret: Optional[str] = None,
        code: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        refresh_token: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        scope: Optional[str] = None,
        code_verifier: Optional[str] = None,
    ) -> OAuth2Token:
        """Handle token request."""
        # Validate client
        client = self._clients.get(client_id)
        if not client:
            raise OAuth2Error("invalid_client", "Unknown client")

        if client_secret and client.client_secret != client_secret:
            raise OAuth2Error("invalid_client", "Invalid client secret")

        if grant_type not in client.grant_types:
            raise OAuth2Error("unauthorized_client", "Grant type not allowed")

        if grant_type == OAuth2GrantType.AUTHORIZATION_CODE:
            return self._exchange_code(client, code, redirect_uri, code_verifier)
        elif grant_type == OAuth2GrantType.CLIENT_CREDENTIALS:
            return self._client_credentials(client, scope)
        elif grant_type == OAuth2GrantType.REFRESH_TOKEN:
            return self._refresh(client, refresh_token)
        elif grant_type == OAuth2GrantType.PASSWORD:
            return self._password_grant(client, username, password, scope)
        else:
            raise OAuth2Error("unsupported_grant_type", "Grant type not supported")

    def _exchange_code(
        self,
        client: OAuth2Client,
        code: Optional[str],
        redirect_uri: Optional[str],
        code_verifier: Optional[str],
    ) -> OAuth2Token:
        """Exchange authorization code for tokens."""
        if not code:
            raise OAuth2Error("invalid_request", "Code required")

        auth_code = self._codes.get(code)
        if not auth_code:
            raise OAuth2Error("invalid_grant", "Invalid code")

        if time.time() > auth_code.expires_at:
            del self._codes[code]
            raise OAuth2Error("invalid_grant", "Code expired")

        if auth_code.client_id != client.client_id:
            raise OAuth2Error("invalid_grant", "Client mismatch")

        if auth_code.redirect_uri != redirect_uri:
            raise OAuth2Error("invalid_grant", "Redirect URI mismatch")

        # Verify PKCE if used
        if auth_code.code_challenge:
            if not code_verifier:
                raise OAuth2Error("invalid_request", "Code verifier required")

            if auth_code.code_challenge_method == "S256":
                challenge = base64.urlsafe_b64encode(
                    hashlib.sha256(code_verifier.encode()).digest()
                ).rstrip(b"=").decode()
            else:
                challenge = code_verifier

            if challenge != auth_code.code_challenge:
                raise OAuth2Error("invalid_grant", "Invalid code verifier")

        # Generate tokens
        del self._codes[code]
        return self._generate_token(
            client.client_id,
            auth_code.user_id,
            auth_code.scope,
        )

    def _client_credentials(
        self,
        client: OAuth2Client,
        scope: Optional[str],
    ) -> OAuth2Token:
        """Handle client credentials grant."""
        return self._generate_token(
            client.client_id,
            client.client_id,  # Client is the user
            scope or " ".join(client.scopes),
        )

    def _refresh(
        self,
        client: OAuth2Client,
        refresh_token: Optional[str],
    ) -> OAuth2Token:
        """Handle refresh token grant."""
        if not refresh_token:
            raise OAuth2Error("invalid_request", "Refresh token required")

        token_data = self._refresh_tokens.get(refresh_token)
        if not token_data:
            raise OAuth2Error("invalid_grant", "Invalid refresh token")

        if time.time() > token_data["expires_at"]:
            del self._refresh_tokens[refresh_token]
            raise OAuth2Error("invalid_grant", "Refresh token expired")

        if token_data["client_id"] != client.client_id:
            raise OAuth2Error("invalid_grant", "Client mismatch")

        # Generate new tokens
        del self._refresh_tokens[refresh_token]
        return self._generate_token(
            client.client_id,
            token_data["user_id"],
            token_data["scope"],
        )

    def _password_grant(
        self,
        client: OAuth2Client,
        username: Optional[str],
        password: Optional[str],
        scope: Optional[str],
    ) -> OAuth2Token:
        """Handle password grant (requires custom validator)."""
        raise OAuth2Error(
            "unsupported_grant_type",
            "Password grant requires custom implementation",
        )

    def _generate_token(
        self,
        client_id: str,
        user_id: str,
        scope: str,
    ) -> OAuth2Token:
        """Generate access and refresh tokens."""
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)

        expires_at = time.time() + self.config.token_expiry
        refresh_expires_at = time.time() + self.config.refresh_token_expiry

        self._tokens[access_token] = {
            "client_id": client_id,
            "user_id": user_id,
            "scope": scope,
            "expires_at": expires_at,
        }

        self._refresh_tokens[refresh_token] = {
            "client_id": client_id,
            "user_id": user_id,
            "scope": scope,
            "expires_at": refresh_expires_at,
        }

        return OAuth2Token(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.config.token_expiry,
            scope=scope,
        )

    def revoke_token(self, token: str) -> bool:
        """Revoke a token."""
        if token in self._tokens:
            del self._tokens[token]
            return True
        if token in self._refresh_tokens:
            del self._refresh_tokens[token]
            return True
        return False


class OAuth2Error(Exception):
    """OAuth2 error."""

    def __init__(self, error: str, description: str):
        self.error = error
        self.description = description
        super().__init__(f"{error}: {description}")


__all__ = [
    "OAuth2Provider",
    "OAuth2Config",
    "OAuth2Token",
    "OAuth2Client",
    "OAuth2GrantType",
    "OAuth2ResponseType",
    "OAuth2Error",
    "AuthorizationCode",
]
