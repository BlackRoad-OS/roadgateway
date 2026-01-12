"""JWT Authentication - JSON Web Token auth provider.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set

from roadgateway_core.security.auth import AuthProvider, AuthResult, AuthStatus

logger = logging.getLogger(__name__)


class JWTAlgorithm(Enum):
    """JWT signing algorithms."""

    HS256 = "HS256"
    HS384 = "HS384"
    HS512 = "HS512"
    RS256 = "RS256"
    RS384 = "RS384"
    RS512 = "RS512"
    ES256 = "ES256"
    ES384 = "ES384"
    ES512 = "ES512"


@dataclass
class JWTConfig:
    """JWT configuration."""

    secret_key: str = ""
    public_key: Optional[str] = None
    algorithm: JWTAlgorithm = JWTAlgorithm.HS256
    issuer: Optional[str] = None
    audience: Optional[str] = None
    leeway: int = 0  # Seconds of leeway for expiration
    verify_exp: bool = True
    verify_nbf: bool = True
    verify_iat: bool = True
    required_claims: Set[str] = field(default_factory=set)


@dataclass
class JWTClaims:
    """JWT claims (payload)."""

    sub: Optional[str] = None  # Subject
    iss: Optional[str] = None  # Issuer
    aud: Optional[str] = None  # Audience
    exp: Optional[int] = None  # Expiration
    nbf: Optional[int] = None  # Not before
    iat: Optional[int] = None  # Issued at
    jti: Optional[str] = None  # JWT ID
    custom: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {}
        if self.sub:
            result["sub"] = self.sub
        if self.iss:
            result["iss"] = self.iss
        if self.aud:
            result["aud"] = self.aud
        if self.exp:
            result["exp"] = self.exp
        if self.nbf:
            result["nbf"] = self.nbf
        if self.iat:
            result["iat"] = self.iat
        if self.jti:
            result["jti"] = self.jti
        result.update(self.custom)
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JWTClaims":
        """Create from dictionary."""
        standard = {"sub", "iss", "aud", "exp", "nbf", "iat", "jti"}
        custom = {k: v for k, v in data.items() if k not in standard}
        return cls(
            sub=data.get("sub"),
            iss=data.get("iss"),
            aud=data.get("aud"),
            exp=data.get("exp"),
            nbf=data.get("nbf"),
            iat=data.get("iat"),
            jti=data.get("jti"),
            custom=custom,
        )


class JWTAuth(AuthProvider):
    """JWT Authentication Provider.

    Features:
    - HMAC and RSA signing
    - Claim validation
    - Token refresh
    - Blacklist support

    JWT Structure:
    ┌────────────────────────────────────────────────────────────┐
    │                        JWT Token                            │
    ├────────────────────────────────────────────────────────────┤
    │  ┌──────────────┐ . ┌──────────────┐ . ┌──────────────┐   │
    │  │    Header    │   │   Payload    │   │  Signature   │   │
    │  │              │   │              │   │              │   │
    │  │ - alg        │   │ - sub        │   │ HMACSHA256(  │   │
    │  │ - typ        │   │ - exp        │   │   header +   │   │
    │  │              │   │ - iat        │   │   payload,   │   │
    │  │              │   │ - claims     │   │   secret     │   │
    │  │              │   │              │   │ )            │   │
    │  └──────────────┘   └──────────────┘   └──────────────┘   │
    └────────────────────────────────────────────────────────────┘
    """

    def __init__(self, config: JWTConfig):
        self.config = config
        self._blacklist: Set[str] = set()

    def authenticate(self, request: Dict[str, Any]) -> AuthResult:
        """Authenticate using JWT."""
        token = self.get_credentials(request)

        if not token:
            return AuthResult(
                status=AuthStatus.MISSING,
                error="No JWT token provided",
            )

        # Check blacklist
        if token in self._blacklist:
            return AuthResult(
                status=AuthStatus.FAILED,
                error="Token has been revoked",
            )

        try:
            claims = self.decode(token)
            return AuthResult(
                status=AuthStatus.SUCCESS,
                identity=claims.sub,
                claims=claims.to_dict(),
                expires_at=float(claims.exp) if claims.exp else None,
            )
        except JWTError as e:
            if "expired" in str(e).lower():
                return AuthResult(
                    status=AuthStatus.EXPIRED,
                    error=str(e),
                )
            return AuthResult(
                status=AuthStatus.INVALID,
                error=str(e),
            )

    def get_credentials(self, request: Dict[str, Any]) -> Optional[str]:
        """Extract JWT from request."""
        headers = request.get("headers", {})
        auth_header = headers.get("Authorization", "")

        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        return None

    def encode(self, claims: JWTClaims) -> str:
        """Encode claims to JWT token."""
        # Create header
        header = {
            "alg": self.config.algorithm.value,
            "typ": "JWT",
        }

        # Set timestamps if not provided
        now = int(time.time())
        payload = claims.to_dict()
        
        if "iat" not in payload:
            payload["iat"] = now

        if self.config.issuer and "iss" not in payload:
            payload["iss"] = self.config.issuer

        # Encode header and payload
        header_b64 = self._b64_encode(json.dumps(header))
        payload_b64 = self._b64_encode(json.dumps(payload))

        # Create signature
        message = f"{header_b64}.{payload_b64}"
        signature = self._sign(message)
        signature_b64 = self._b64_encode(signature)

        return f"{header_b64}.{payload_b64}.{signature_b64}"

    def decode(self, token: str) -> JWTClaims:
        """Decode and verify JWT token."""
        parts = token.split(".")
        if len(parts) != 3:
            raise JWTError("Invalid token format")

        header_b64, payload_b64, signature_b64 = parts

        # Verify signature
        message = f"{header_b64}.{payload_b64}"
        expected_sig = self._b64_decode(signature_b64)
        
        if not self._verify(message, expected_sig):
            raise JWTError("Invalid signature")

        # Decode header
        try:
            header = json.loads(self._b64_decode(header_b64))
        except Exception:
            raise JWTError("Invalid header")

        # Verify algorithm
        if header.get("alg") != self.config.algorithm.value:
            raise JWTError(f"Algorithm mismatch: expected {self.config.algorithm.value}")

        # Decode payload
        try:
            payload = json.loads(self._b64_decode(payload_b64))
        except Exception:
            raise JWTError("Invalid payload")

        claims = JWTClaims.from_dict(payload)

        # Validate claims
        self._validate_claims(claims)

        return claims

    def _validate_claims(self, claims: JWTClaims) -> None:
        """Validate JWT claims."""
        now = int(time.time())

        # Check expiration
        if self.config.verify_exp and claims.exp:
            if now > claims.exp + self.config.leeway:
                raise JWTError("Token has expired")

        # Check not before
        if self.config.verify_nbf and claims.nbf:
            if now < claims.nbf - self.config.leeway:
                raise JWTError("Token not yet valid")

        # Check issued at
        if self.config.verify_iat and claims.iat:
            if claims.iat > now + self.config.leeway:
                raise JWTError("Token issued in the future")

        # Check issuer
        if self.config.issuer and claims.iss:
            if claims.iss != self.config.issuer:
                raise JWTError("Invalid issuer")

        # Check audience
        if self.config.audience and claims.aud:
            if claims.aud != self.config.audience:
                raise JWTError("Invalid audience")

        # Check required claims
        claims_dict = claims.to_dict()
        for required in self.config.required_claims:
            if required not in claims_dict:
                raise JWTError(f"Missing required claim: {required}")

    def _sign(self, message: str) -> bytes:
        """Sign message with configured algorithm."""
        if self.config.algorithm in (JWTAlgorithm.HS256, JWTAlgorithm.HS384, JWTAlgorithm.HS512):
            hash_alg = {
                JWTAlgorithm.HS256: hashlib.sha256,
                JWTAlgorithm.HS384: hashlib.sha384,
                JWTAlgorithm.HS512: hashlib.sha512,
            }[self.config.algorithm]

            return hmac.new(
                self.config.secret_key.encode(),
                message.encode(),
                hash_alg,
            ).digest()
        else:
            raise JWTError(f"Algorithm {self.config.algorithm} not implemented")

    def _verify(self, message: str, signature: bytes) -> bool:
        """Verify message signature."""
        expected = self._sign(message)
        return hmac.compare_digest(expected, signature)

    def _b64_encode(self, data: Any) -> str:
        """Base64url encode."""
        if isinstance(data, str):
            data = data.encode()
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    def _b64_decode(self, data: str) -> bytes:
        """Base64url decode."""
        padding = 4 - len(data) % 4
        if padding != 4:
            data += "=" * padding
        return base64.urlsafe_b64decode(data)

    def blacklist(self, token: str) -> None:
        """Add token to blacklist."""
        self._blacklist.add(token)

    def create_token(
        self,
        subject: str,
        expires_in: int = 3600,
        claims: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new JWT token."""
        now = int(time.time())
        jwt_claims = JWTClaims(
            sub=subject,
            iat=now,
            exp=now + expires_in,
            custom=claims or {},
        )
        return self.encode(jwt_claims)


class JWTError(Exception):
    """JWT related error."""
    pass


__all__ = [
    "JWTAuth",
    "JWTConfig",
    "JWTClaims",
    "JWTAlgorithm",
    "JWTError",
]
