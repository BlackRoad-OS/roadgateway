"""Security module - Authentication and authorization."""

from roadgateway_core.security.auth import (
    AuthProvider,
    AuthResult,
    BasicAuth,
    APIKeyAuth,
    BearerTokenAuth,
)
from roadgateway_core.security.jwt import (
    JWTAuth,
    JWTConfig,
    JWTClaims,
)
from roadgateway_core.security.oauth import (
    OAuth2Provider,
    OAuth2Config,
    OAuth2Token,
)
from roadgateway_core.security.acl import (
    AccessControl,
    Permission,
    Role,
    Policy,
)

__all__ = [
    "AuthProvider",
    "AuthResult",
    "BasicAuth",
    "APIKeyAuth",
    "BearerTokenAuth",
    "JWTAuth",
    "JWTConfig",
    "JWTClaims",
    "OAuth2Provider",
    "OAuth2Config",
    "OAuth2Token",
    "AccessControl",
    "Permission",
    "Role",
    "Policy",
]
