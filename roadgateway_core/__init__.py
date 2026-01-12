"""RoadGateway - Enterprise API Gateway.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.

RoadGateway provides a high-performance API gateway with:
- Request routing and load balancing
- Rate limiting and throttling
- Authentication (JWT, OAuth2, API keys)
- Circuit breaker and retry patterns
- Health monitoring and metrics
- Plugin system for extensibility

Architecture Overview:
┌─────────────────────────────────────────────────────────────────────────────┐
│                            RoadGateway                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                        Request Pipeline                                │  │
│  │  Client ──▶ Gateway ──▶ Middleware ──▶ Router ──▶ Backend ──▶ Client  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐ │
│  │    Gateway      │  │   Middleware    │  │        Routing              │ │
│  │                 │  │                 │  │                             │ │
│  │ - Server        │  │ - Logging       │  │ - Pattern matching          │ │
│  │ - Request       │  │ - CORS          │  │ - Path parameters           │ │
│  │ - Response      │  │ - Transform     │  │ - Query routing             │ │
│  │ - Config        │  │ - Auth          │  │ - Header routing            │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘ │
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐ │
│  │  Rate Limiting  │  │  Load Balancing │  │        Security             │ │
│  │                 │  │                 │  │                             │ │
│  │ - Token bucket  │  │ - Round robin   │  │ - Basic/API Key auth        │ │
│  │ - Sliding       │  │ - Weighted      │  │ - JWT/OAuth2                │ │
│  │ - Leaky bucket  │  │ - Least conn    │  │ - ACL/RBAC                  │ │
│  │ - Fixed window  │  │ - IP hash       │  │ - Rate limiting             │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘ │
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐ │
│  │     Proxy       │  │     Health      │  │        Metrics              │ │
│  │                 │  │                 │  │                             │ │
│  │ - Forwarding    │  │ - Health checks │  │ - Counters                  │ │
│  │ - Circuit break │  │ - Readiness     │  │ - Gauges                    │ │
│  │ - Retry logic   │  │ - Liveness      │  │ - Histograms                │ │
│  │ - Streaming     │  │ - Startup       │  │ - Prometheus export         │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘ │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                          Plugin System                                │  │
│  │  STARTUP ──▶ PRE_REQUEST ──▶ ROUTING ──▶ POST_RESPONSE ──▶ SHUTDOWN  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

Request Flow:
1. Client sends request to Gateway
2. Middleware chain processes request (logging, auth, transform)
3. Router matches route and selects backend
4. Load balancer chooses healthy backend
5. Proxy forwards request with retry/circuit breaker
6. Response flows back through middleware
7. Metrics recorded, response sent to client

Usage:
    from roadgateway_core import Gateway, Route, RateLimiter
    
    gateway = Gateway()
    
    # Add routes
    gateway.route("/api/v1/*", targets=["backend-1:8080", "backend-2:8080"])
    gateway.route("/static/*", targets=["cdn:443"])
    
    # Add middleware
    gateway.use(RateLimiterMiddleware(requests_per_minute=1000))
    gateway.use(JWTAuthMiddleware(secret="..."))
    gateway.use(CORSMiddleware(origins=["*"]))
    
    # Start gateway
    gateway.run(host="0.0.0.0", port=8080)
"""

__version__ = "0.1.0"
__author__ = "BlackRoad OS, Inc."

# Gateway core
from roadgateway_core.gateway.server import Gateway, GatewayConfig
from roadgateway_core.gateway.request import Request, Response

# Routing
from roadgateway_core.routing.router import Router, Route
from roadgateway_core.routing.matcher import PatternMatcher, RouteMatcher

# Middleware
from roadgateway_core.middleware.base import Middleware, MiddlewareChain
from roadgateway_core.middleware.logging import LoggingMiddleware
from roadgateway_core.middleware.cors import CORSMiddleware
from roadgateway_core.middleware.transform import TransformMiddleware

# Rate limiting
from roadgateway_core.ratelimit.limiter import RateLimiter
from roadgateway_core.ratelimit.algorithms import TokenBucket, SlidingWindow
from roadgateway_core.ratelimit.middleware import RateLimiterMiddleware

# Load balancing
from roadgateway_core.loadbalancing.balancer import (
    LoadBalancer,
    RoundRobinBalancer,
    WeightedRoundRobinBalancer,
    LeastConnectionsBalancer,
)
from roadgateway_core.loadbalancing.pool import BackendPool, Backend

# Proxy
from roadgateway_core.proxy.forwarder import Proxy, ProxyConfig
from roadgateway_core.proxy.circuit_breaker import CircuitBreaker, CircuitState
from roadgateway_core.proxy.retry import RetryPolicy, BackoffStrategy

# Security
from roadgateway_core.security.auth import (
    AuthProvider,
    BasicAuth,
    APIKeyAuth,
    BearerTokenAuth,
)
from roadgateway_core.security.jwt import JWTAuth, JWTConfig
from roadgateway_core.security.oauth import OAuth2Provider
from roadgateway_core.security.acl import AccessControl, Role, Permission

# Health
from roadgateway_core.health.checker import HealthChecker, HealthStatus
from roadgateway_core.health.readiness import ReadinessProbe, LivenessProbe

# Metrics
from roadgateway_core.metrics.collector import MetricsCollector, Counter, Gauge
from roadgateway_core.metrics.exporter import PrometheusExporter

# Plugins
from roadgateway_core.plugins.base import Plugin, PluginManager
from roadgateway_core.plugins.loader import PluginLoader

# Utils
from roadgateway_core.utils.config import Config, load_config

__all__ = [
    # Version
    "__version__",
    # Gateway
    "Gateway",
    "GatewayConfig",
    "Request",
    "Response",
    # Routing
    "Router",
    "Route",
    "PatternMatcher",
    "RouteMatcher",
    # Middleware
    "Middleware",
    "MiddlewareChain",
    "LoggingMiddleware",
    "CORSMiddleware",
    "TransformMiddleware",
    # Rate limiting
    "RateLimiter",
    "TokenBucket",
    "SlidingWindow",
    "RateLimiterMiddleware",
    # Load balancing
    "LoadBalancer",
    "RoundRobinBalancer",
    "WeightedRoundRobinBalancer",
    "LeastConnectionsBalancer",
    "BackendPool",
    "Backend",
    # Proxy
    "Proxy",
    "ProxyConfig",
    "CircuitBreaker",
    "CircuitState",
    "RetryPolicy",
    "BackoffStrategy",
    # Security
    "AuthProvider",
    "BasicAuth",
    "APIKeyAuth",
    "BearerTokenAuth",
    "JWTAuth",
    "JWTConfig",
    "OAuth2Provider",
    "AccessControl",
    "Role",
    "Permission",
    # Health
    "HealthChecker",
    "HealthStatus",
    "ReadinessProbe",
    "LivenessProbe",
    # Metrics
    "MetricsCollector",
    "Counter",
    "Gauge",
    "PrometheusExporter",
    # Plugins
    "Plugin",
    "PluginManager",
    "PluginLoader",
    # Utils
    "Config",
    "load_config",
]
