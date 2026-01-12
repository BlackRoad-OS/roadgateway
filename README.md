# RoadGateway

Enterprise API Gateway for BlackRoad OS.

## Features

- **Request Routing** - Pattern-based routing with path parameters
- **Load Balancing** - Round-robin, weighted, least connections, IP hash
- **Rate Limiting** - Token bucket, sliding window, leaky bucket algorithms
- **Authentication** - Basic, API key, JWT, OAuth2 support
- **Authorization** - Role-based access control (RBAC)
- **Circuit Breaker** - Failure protection with automatic recovery
- **Retry Policies** - Configurable backoff strategies
- **Health Checks** - TCP, HTTP, gRPC health monitoring
- **Metrics** - Prometheus-compatible metrics export
- **Plugin System** - Extensible hook-based architecture

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            RoadGateway                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Client ──▶ Gateway ──▶ Middleware ──▶ Router ──▶ Backend ──▶ Client   │
│                                                                          │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐               │
│  │ Rate Limiting │  │ Load Balance  │  │   Security    │               │
│  │               │  │               │  │               │               │
│  │ Token Bucket  │  │ Round Robin   │  │ JWT/OAuth2    │               │
│  │ Sliding Win   │  │ Least Conn    │  │ API Keys      │               │
│  └───────────────┘  └───────────────┘  └───────────────┘               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Installation

```bash
pip install roadgateway
```

## Quick Start

```python
from roadgateway_core import Gateway, Route

# Create gateway
gateway = Gateway()

# Add routes
gateway.route("/api/v1/*", targets=["backend-1:8080", "backend-2:8080"])
gateway.route("/static/*", targets=["cdn:443"])

# Start gateway
gateway.run(host="0.0.0.0", port=8080)
```

## Load Balancing

```python
from roadgateway_core import RoundRobinBalancer, BackendServer

balancer = RoundRobinBalancer()
balancer.add_server(BackendServer("server1", 8080, weight=2))
balancer.add_server(BackendServer("server2", 8080, weight=1))

# Select backend
server = balancer.select()
```

## Rate Limiting

```python
from roadgateway_core import RateLimiter, TokenBucket

limiter = RateLimiter(
    algorithm=TokenBucket(capacity=100, refill_rate=10)
)

if limiter.allow("user-123"):
    # Process request
    pass
```

## Authentication

```python
from roadgateway_core import JWTAuth, JWTConfig

auth = JWTAuth(JWTConfig(
    secret_key="your-secret",
    algorithm="HS256",
))

# Create token
token = auth.create_token(subject="user-123", expires_in=3600)

# Verify token
result = auth.authenticate({"headers": {"Authorization": f"Bearer {token}"}})
```

## Circuit Breaker

```python
from roadgateway_core import CircuitBreaker

breaker = CircuitBreaker("backend-service")

try:
    result = breaker.call(make_request)
except CircuitBreakerError:
    # Circuit is open, handle gracefully
    pass
```

## Health Checks

```python
from roadgateway_core import HealthChecker, tcp_check, http_check

checker = HealthChecker()
checker.add_check(tcp_check("database", "db.local", 5432))
checker.add_check(http_check("api", "http://api.local/health"))

# Check all
results = checker.check_all()
```

## Metrics

```python
from roadgateway_core import MetricsCollector, PrometheusExporter

collector = MetricsCollector(prefix="gateway")
requests = collector.counter("requests_total", labels=["method", "status"])

requests.inc(labels={"method": "GET", "status": "200"})

# Export to Prometheus format
exporter = PrometheusExporter()
print(exporter.export(collector))
```

## Plugin System

```python
from roadgateway_core import Plugin, PluginManager

class MyPlugin(Plugin):
    name = "my_plugin"
    
    def pre_request(self, request):
        # Modify request
        return request
    
    def post_request(self, request, response):
        # Modify response
        return response

manager = PluginManager()
manager.register(MyPlugin())
```

## Configuration

```python
from roadgateway_core import Config, load_config

# Load from file
config = load_config("config.yaml")

# Or from environment
config = Config.from_env(prefix="GATEWAY_")

# Access settings
print(config.port)  # 8080
print(config.rate_limit_enabled)  # True
```

## License

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
