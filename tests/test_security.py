"""Security tests."""

import pytest
from roadgateway_core.security.auth import BasicAuth, APIKeyAuth
from roadgateway_core.security.jwt import JWTAuth, JWTConfig, JWTClaims


class TestBasicAuth:
    """Test Basic authentication."""

    def test_authenticate_valid(self):
        """Test valid authentication."""
        auth = BasicAuth()
        auth.add_user("admin", "password123")
        
        import base64
        creds = base64.b64encode(b"admin:password123").decode()
        
        result = auth.authenticate({
            "headers": {"Authorization": f"Basic {creds}"}
        })
        
        assert result.is_authenticated
        assert result.identity == "admin"


class TestAPIKeyAuth:
    """Test API key authentication."""

    def test_authenticate_valid_key(self):
        """Test valid API key."""
        auth = APIKeyAuth()
        auth.add_key("test-key-123", "user1")
        
        result = auth.authenticate({
            "headers": {"X-API-Key": "test-key-123"}
        })
        
        assert result.is_authenticated
        assert result.identity == "user1"


class TestJWTAuth:
    """Test JWT authentication."""

    def test_create_and_verify_token(self):
        """Test creating and verifying JWT."""
        config = JWTConfig(secret_key="test-secret")
        auth = JWTAuth(config)
        
        token = auth.create_token("user-123", expires_in=3600)
        
        result = auth.authenticate({
            "headers": {"Authorization": f"Bearer {token}"}
        })
        
        assert result.is_authenticated
        assert result.identity == "user-123"
