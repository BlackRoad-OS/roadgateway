"""Gateway tests."""

import pytest
from roadgateway_core.gateway.server import Gateway, GatewayConfig
from roadgateway_core.gateway.request import Request, Response


class TestGateway:
    """Test Gateway class."""

    def test_create_gateway(self):
        """Test gateway creation."""
        gateway = Gateway()
        assert gateway is not None

    def test_gateway_with_config(self):
        """Test gateway with custom config."""
        config = GatewayConfig(host="127.0.0.1", port=9000)
        gateway = Gateway(config)
        assert gateway.config.port == 9000

    def test_add_route(self):
        """Test adding routes."""
        gateway = Gateway()
        gateway.route("/api/*", targets=["backend:8080"])
        assert len(gateway._routes) == 1


class TestRequest:
    """Test Request class."""

    def test_create_request(self):
        """Test request creation."""
        request = Request(
            method="GET",
            path="/api/users",
            headers={"Content-Type": "application/json"},
        )
        assert request.method == "GET"
        assert request.path == "/api/users"

    def test_request_query_params(self):
        """Test query parameter parsing."""
        request = Request(
            method="GET",
            path="/api/users",
            query={"page": "1", "limit": "10"},
        )
        assert request.query["page"] == "1"


class TestResponse:
    """Test Response class."""

    def test_create_response(self):
        """Test response creation."""
        response = Response(status=200, body=b"OK")
        assert response.status == 200
        assert response.body == b"OK"

    def test_response_json(self):
        """Test JSON response."""
        response = Response.json({"message": "success"})
        assert response.status == 200
        assert b"message" in response.body
