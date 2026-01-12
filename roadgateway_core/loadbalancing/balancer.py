"""Load Balancer - Distribution algorithms for backend servers.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import hashlib
import logging
import random
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class BalancingAlgorithm(Enum):
    """Load balancing algorithms."""

    ROUND_ROBIN = auto()
    WEIGHTED_ROUND_ROBIN = auto()
    LEAST_CONNECTIONS = auto()
    RANDOM = auto()
    IP_HASH = auto()
    LEAST_RESPONSE_TIME = auto()
    RESOURCE_BASED = auto()


@dataclass
class BalancerConfig:
    """Load balancer configuration."""

    algorithm: BalancingAlgorithm = BalancingAlgorithm.ROUND_ROBIN
    health_check_interval: float = 10.0
    max_fails: int = 3
    fail_timeout: float = 30.0
    sticky_sessions: bool = False
    session_cookie: str = "SERVERID"


@dataclass
class BackendServer:
    """Backend server representation."""

    host: str
    port: int
    weight: int = 1
    max_connections: int = 1000
    active_connections: int = 0
    total_requests: int = 0
    failed_requests: int = 0
    avg_response_time: float = 0.0
    is_healthy: bool = True
    last_health_check: float = 0.0
    consecutive_failures: int = 0

    @property
    def address(self) -> str:
        """Get server address."""
        return f"{self.host}:{self.port}"

    @property
    def available_capacity(self) -> int:
        """Get available connection capacity."""
        return max(0, self.max_connections - self.active_connections)

    def record_request(self, response_time: float, success: bool) -> None:
        """Record request statistics."""
        self.total_requests += 1
        
        if success:
            self.consecutive_failures = 0
            # Exponential moving average for response time
            alpha = 0.1
            self.avg_response_time = (
                alpha * response_time + (1 - alpha) * self.avg_response_time
            )
        else:
            self.failed_requests += 1
            self.consecutive_failures += 1


class LoadBalancer(ABC):
    """Abstract load balancer.

    Architecture:
    ┌────────────────────────────────────────────────────────────┐
    │                     Load Balancer                           │
    ├────────────────────────────────────────────────────────────┤
    │  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   │
    │  │   Backend    │   │   Backend    │   │   Backend    │   │
    │  │   Pool       │   │   Selection  │   │   Monitor    │   │
    │  │              │   │              │   │              │   │
    │  │ - Servers    │   │ - Algorithm  │   │ - Health     │   │
    │  │ - Health     │   │ - Weights    │   │ - Metrics    │   │
    │  │ - Stats      │   │ - Sessions   │   │ - Alerts     │   │
    │  └──────────────┘   └──────────────┘   └──────────────┘   │
    └────────────────────────────────────────────────────────────┘
    """

    def __init__(self, config: Optional[BalancerConfig] = None):
        self.config = config or BalancerConfig()
        self._servers: List[BackendServer] = []
        self._lock = threading.RLock()

    def add_server(self, server: BackendServer) -> "LoadBalancer":
        """Add a backend server."""
        with self._lock:
            self._servers.append(server)
        return self

    def remove_server(self, address: str) -> bool:
        """Remove a backend server by address."""
        with self._lock:
            for i, server in enumerate(self._servers):
                if server.address == address:
                    self._servers.pop(i)
                    return True
        return False

    def get_healthy_servers(self) -> List[BackendServer]:
        """Get list of healthy servers."""
        with self._lock:
            return [s for s in self._servers if s.is_healthy]

    @abstractmethod
    def select(self, client_ip: Optional[str] = None) -> Optional[BackendServer]:
        """Select a backend server."""
        pass

    def mark_healthy(self, address: str) -> None:
        """Mark server as healthy."""
        with self._lock:
            for server in self._servers:
                if server.address == address:
                    server.is_healthy = True
                    server.consecutive_failures = 0
                    break

    def mark_unhealthy(self, address: str) -> None:
        """Mark server as unhealthy."""
        with self._lock:
            for server in self._servers:
                if server.address == address:
                    server.is_healthy = False
                    break

    def connect(self, server: BackendServer) -> None:
        """Record connection to server."""
        with self._lock:
            server.active_connections += 1

    def disconnect(self, server: BackendServer) -> None:
        """Record disconnection from server."""
        with self._lock:
            server.active_connections = max(0, server.active_connections - 1)

    def get_stats(self) -> Dict[str, Any]:
        """Get load balancer statistics."""
        with self._lock:
            healthy = len([s for s in self._servers if s.is_healthy])
            total = len(self._servers)
            
            return {
                "total_servers": total,
                "healthy_servers": healthy,
                "unhealthy_servers": total - healthy,
                "total_connections": sum(s.active_connections for s in self._servers),
                "total_requests": sum(s.total_requests for s in self._servers),
                "servers": [
                    {
                        "address": s.address,
                        "healthy": s.is_healthy,
                        "connections": s.active_connections,
                        "requests": s.total_requests,
                        "avg_response_time": s.avg_response_time,
                    }
                    for s in self._servers
                ],
            }


class RoundRobinBalancer(LoadBalancer):
    """Round-robin load balancer.

    Distributes requests sequentially across all healthy servers.
    """

    def __init__(self, config: Optional[BalancerConfig] = None):
        super().__init__(config)
        self._index = 0

    def select(self, client_ip: Optional[str] = None) -> Optional[BackendServer]:
        """Select next server in rotation."""
        healthy = self.get_healthy_servers()
        
        if not healthy:
            return None

        with self._lock:
            server = healthy[self._index % len(healthy)]
            self._index = (self._index + 1) % len(healthy)
            return server


class WeightedRoundRobinBalancer(LoadBalancer):
    """Weighted round-robin load balancer.

    Distributes requests based on server weights.
    Higher weight = more requests.
    """

    def __init__(self, config: Optional[BalancerConfig] = None):
        super().__init__(config)
        self._current_weight = 0
        self._index = -1

    def select(self, client_ip: Optional[str] = None) -> Optional[BackendServer]:
        """Select server based on weights."""
        healthy = self.get_healthy_servers()
        
        if not healthy:
            return None

        with self._lock:
            max_weight = max(s.weight for s in healthy)
            gcd_weight = self._gcd_weights(healthy)

            while True:
                self._index = (self._index + 1) % len(healthy)
                
                if self._index == 0:
                    self._current_weight -= gcd_weight
                    if self._current_weight <= 0:
                        self._current_weight = max_weight

                server = healthy[self._index]
                if server.weight >= self._current_weight:
                    return server

    def _gcd_weights(self, servers: List[BackendServer]) -> int:
        """Calculate GCD of all weights."""
        from math import gcd
        from functools import reduce
        
        weights = [s.weight for s in servers]
        return reduce(gcd, weights)


class LeastConnectionsBalancer(LoadBalancer):
    """Least connections load balancer.

    Routes to the server with fewest active connections.
    """

    def select(self, client_ip: Optional[str] = None) -> Optional[BackendServer]:
        """Select server with least connections."""
        healthy = self.get_healthy_servers()
        
        if not healthy:
            return None

        with self._lock:
            return min(healthy, key=lambda s: s.active_connections)


class WeightedLeastConnectionsBalancer(LoadBalancer):
    """Weighted least connections balancer.

    Considers both connection count and server weight.
    Score = connections / weight (lower is better).
    """

    def select(self, client_ip: Optional[str] = None) -> Optional[BackendServer]:
        """Select server with best weighted connection ratio."""
        healthy = self.get_healthy_servers()
        
        if not healthy:
            return None

        with self._lock:
            return min(
                healthy,
                key=lambda s: s.active_connections / max(s.weight, 1)
            )


class RandomBalancer(LoadBalancer):
    """Random load balancer.

    Randomly selects from healthy servers.
    """

    def select(self, client_ip: Optional[str] = None) -> Optional[BackendServer]:
        """Select random server."""
        healthy = self.get_healthy_servers()
        
        if not healthy:
            return None

        return random.choice(healthy)


class WeightedRandomBalancer(LoadBalancer):
    """Weighted random load balancer.

    Random selection weighted by server weights.
    """

    def select(self, client_ip: Optional[str] = None) -> Optional[BackendServer]:
        """Select random server based on weights."""
        healthy = self.get_healthy_servers()
        
        if not healthy:
            return None

        total_weight = sum(s.weight for s in healthy)
        rand = random.uniform(0, total_weight)
        
        cumulative = 0.0
        for server in healthy:
            cumulative += server.weight
            if rand <= cumulative:
                return server

        return healthy[-1]


class IPHashBalancer(LoadBalancer):
    """IP hash load balancer.

    Routes requests from same client IP to same server.
    Provides session persistence without cookies.
    """

    def select(self, client_ip: Optional[str] = None) -> Optional[BackendServer]:
        """Select server based on client IP hash."""
        healthy = self.get_healthy_servers()
        
        if not healthy:
            return None

        if not client_ip:
            return random.choice(healthy)

        # Hash the IP address
        hash_value = int(
            hashlib.md5(client_ip.encode()).hexdigest(), 16
        )
        index = hash_value % len(healthy)
        
        return healthy[index]


class LeastResponseTimeBalancer(LoadBalancer):
    """Least response time load balancer.

    Routes to server with lowest average response time.
    """

    def select(self, client_ip: Optional[str] = None) -> Optional[BackendServer]:
        """Select server with lowest response time."""
        healthy = self.get_healthy_servers()
        
        if not healthy:
            return None

        with self._lock:
            # Prefer servers with requests (have response time data)
            with_data = [s for s in healthy if s.total_requests > 0]
            
            if with_data:
                return min(with_data, key=lambda s: s.avg_response_time)
            else:
                return random.choice(healthy)


class ResourceBasedBalancer(LoadBalancer):
    """Resource-based load balancer.

    Selects based on available capacity and resources.
    """

    def select(self, client_ip: Optional[str] = None) -> Optional[BackendServer]:
        """Select server with most available resources."""
        healthy = self.get_healthy_servers()
        
        if not healthy:
            return None

        with self._lock:
            return max(healthy, key=lambda s: s.available_capacity)


def create_balancer(
    algorithm: BalancingAlgorithm,
    config: Optional[BalancerConfig] = None,
) -> LoadBalancer:
    """Factory function to create load balancer."""
    balancers = {
        BalancingAlgorithm.ROUND_ROBIN: RoundRobinBalancer,
        BalancingAlgorithm.WEIGHTED_ROUND_ROBIN: WeightedRoundRobinBalancer,
        BalancingAlgorithm.LEAST_CONNECTIONS: LeastConnectionsBalancer,
        BalancingAlgorithm.RANDOM: RandomBalancer,
        BalancingAlgorithm.IP_HASH: IPHashBalancer,
        BalancingAlgorithm.LEAST_RESPONSE_TIME: LeastResponseTimeBalancer,
        BalancingAlgorithm.RESOURCE_BASED: ResourceBasedBalancer,
    }

    balancer_class = balancers.get(algorithm, RoundRobinBalancer)
    return balancer_class(config)


__all__ = [
    "LoadBalancer",
    "RoundRobinBalancer",
    "WeightedRoundRobinBalancer",
    "LeastConnectionsBalancer",
    "WeightedLeastConnectionsBalancer",
    "RandomBalancer",
    "WeightedRandomBalancer",
    "IPHashBalancer",
    "LeastResponseTimeBalancer",
    "ResourceBasedBalancer",
    "BalancerConfig",
    "BalancingAlgorithm",
    "BackendServer",
    "create_balancer",
]
