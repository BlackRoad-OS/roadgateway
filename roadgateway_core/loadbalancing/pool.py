"""Backend Pool - Server pool management.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, Iterator, List, Optional, Set

from roadgateway_core.loadbalancing.balancer import BackendServer, LoadBalancer
from roadgateway_core.loadbalancing.health import HealthChecker, HealthStatus

logger = logging.getLogger(__name__)


class BackendStatus(Enum):
    """Backend server status."""

    ACTIVE = auto()
    DRAINING = auto()
    STANDBY = auto()
    DISABLED = auto()
    FAILED = auto()


@dataclass
class Backend:
    """Backend server with metadata."""

    host: str
    port: int
    weight: int = 1
    max_connections: int = 1000
    status: BackendStatus = BackendStatus.ACTIVE
    tags: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Runtime stats
    active_connections: int = 0
    total_requests: int = 0
    total_errors: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    avg_latency_ms: float = 0.0
    last_used: float = 0.0
    health_status: HealthStatus = HealthStatus.UNKNOWN

    @property
    def address(self) -> str:
        """Get server address."""
        return f"{self.host}:{self.port}"

    @property
    def is_available(self) -> bool:
        """Check if server is available for requests."""
        return (
            self.status == BackendStatus.ACTIVE
            and self.health_status == HealthStatus.HEALTHY
            and self.active_connections < self.max_connections
        )

    def to_backend_server(self) -> BackendServer:
        """Convert to BackendServer for load balancer."""
        return BackendServer(
            host=self.host,
            port=self.port,
            weight=self.weight,
            max_connections=self.max_connections,
            active_connections=self.active_connections,
            total_requests=self.total_requests,
            is_healthy=self.health_status == HealthStatus.HEALTHY,
        )


@dataclass
class PoolConfig:
    """Backend pool configuration."""

    name: str = "default"
    max_connections_per_backend: int = 1000
    connection_timeout: float = 30.0
    idle_timeout: float = 300.0
    health_check_interval: float = 10.0
    drain_timeout: float = 60.0


class BackendPool:
    """Backend server pool manager.

    Features:
    - Dynamic backend management
    - Health monitoring integration
    - Connection tracking
    - Graceful draining
    - Tag-based filtering

    Architecture:
    ┌────────────────────────────────────────────────────────────┐
    │                      Backend Pool                           │
    ├────────────────────────────────────────────────────────────┤
    │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │
    │  │Backend 1│ │Backend 2│ │Backend 3│ │Backend N│          │
    │  │ Active  │ │ Active  │ │Draining │ │ Standby │          │
    │  └─────────┘ └─────────┘ └─────────┘ └─────────┘          │
    │                                                             │
    │  ┌─────────────────┐  ┌─────────────────┐                  │
    │  │  Health Check   │  │   Connection    │                  │
    │  │   Integration   │  │    Tracking     │                  │
    │  └─────────────────┘  └─────────────────┘                  │
    └────────────────────────────────────────────────────────────┘
    """

    def __init__(
        self,
        config: Optional[PoolConfig] = None,
        balancer: Optional[LoadBalancer] = None,
        health_checker: Optional[HealthChecker] = None,
    ):
        self.config = config or PoolConfig()
        self.balancer = balancer
        self.health_checker = health_checker
        
        self._backends: Dict[str, Backend] = {}
        self._lock = threading.RLock()
        self._listeners: List[Callable[[str, BackendStatus], None]] = []

        # Register health callback if checker provided
        if self.health_checker:
            self.health_checker.on_status_change(self._on_health_change)

    def add_backend(self, backend: Backend) -> "BackendPool":
        """Add a backend to the pool."""
        with self._lock:
            self._backends[backend.address] = backend
            
            if self.balancer:
                self.balancer.add_server(backend.to_backend_server())
                
            if self.health_checker:
                self.health_checker.add_target(backend.address)

        logger.info(f"Added backend: {backend.address}")
        return self

    def remove_backend(self, address: str) -> bool:
        """Remove a backend from the pool."""
        with self._lock:
            if address not in self._backends:
                return False

            backend = self._backends.pop(address)
            
            if self.balancer:
                self.balancer.remove_server(address)
                
            if self.health_checker:
                self.health_checker.remove_target(address)

        logger.info(f"Removed backend: {address}")
        return True

    def get_backend(self, address: str) -> Optional[Backend]:
        """Get a backend by address."""
        with self._lock:
            return self._backends.get(address)

    def get_backends(
        self,
        status: Optional[BackendStatus] = None,
        tags: Optional[Set[str]] = None,
    ) -> List[Backend]:
        """Get backends with optional filtering."""
        with self._lock:
            backends = list(self._backends.values())

            if status is not None:
                backends = [b for b in backends if b.status == status]

            if tags:
                backends = [b for b in backends if tags <= b.tags]

            return backends

    def get_available_backends(self) -> List[Backend]:
        """Get all available backends."""
        with self._lock:
            return [b for b in self._backends.values() if b.is_available]

    def select_backend(self, client_ip: Optional[str] = None) -> Optional[Backend]:
        """Select a backend using the load balancer."""
        if not self.balancer:
            available = self.get_available_backends()
            return available[0] if available else None

        server = self.balancer.select(client_ip)
        if server:
            return self.get_backend(server.address)
        return None

    def set_status(self, address: str, status: BackendStatus) -> bool:
        """Set backend status."""
        with self._lock:
            backend = self._backends.get(address)
            if not backend:
                return False

            old_status = backend.status
            backend.status = status

            # Update load balancer
            if self.balancer:
                if status in (BackendStatus.ACTIVE,):
                    self.balancer.mark_healthy(address)
                else:
                    self.balancer.mark_unhealthy(address)

        # Notify listeners
        if old_status != status:
            for listener in self._listeners:
                try:
                    listener(address, status)
                except Exception as e:
                    logger.error(f"Listener error: {e}")

        return True

    def drain_backend(self, address: str) -> bool:
        """Start draining a backend (stop new connections)."""
        with self._lock:
            backend = self._backends.get(address)
            if not backend:
                return False

            backend.status = BackendStatus.DRAINING
            
            if self.balancer:
                self.balancer.mark_unhealthy(address)

        logger.info(f"Draining backend: {address}")
        return True

    def enable_backend(self, address: str) -> bool:
        """Enable a backend for traffic."""
        return self.set_status(address, BackendStatus.ACTIVE)

    def disable_backend(self, address: str) -> bool:
        """Disable a backend (no traffic)."""
        return self.set_status(address, BackendStatus.DISABLED)

    def connect(self, backend: Backend) -> bool:
        """Record connection to backend."""
        with self._lock:
            if backend.active_connections >= backend.max_connections:
                return False
            
            backend.active_connections += 1
            backend.last_used = time.time()
            
            if self.balancer:
                self.balancer.connect(backend.to_backend_server())

        return True

    def disconnect(self, backend: Backend) -> None:
        """Record disconnection from backend."""
        with self._lock:
            backend.active_connections = max(0, backend.active_connections - 1)
            
            if self.balancer:
                self.balancer.disconnect(backend.to_backend_server())

    def record_request(
        self,
        backend: Backend,
        success: bool,
        latency_ms: float,
        bytes_in: int = 0,
        bytes_out: int = 0,
    ) -> None:
        """Record request statistics."""
        with self._lock:
            backend.total_requests += 1
            backend.bytes_in += bytes_in
            backend.bytes_out += bytes_out
            
            if not success:
                backend.total_errors += 1
            
            # Exponential moving average for latency
            alpha = 0.1
            backend.avg_latency_ms = (
                alpha * latency_ms + (1 - alpha) * backend.avg_latency_ms
            )

    def on_status_change(
        self,
        callback: Callable[[str, BackendStatus], None],
    ) -> "BackendPool":
        """Register status change listener."""
        self._listeners.append(callback)
        return self

    def _on_health_change(self, address: str, status: HealthStatus) -> None:
        """Handle health status change."""
        with self._lock:
            backend = self._backends.get(address)
            if backend:
                backend.health_status = status
                
                # Update balancer
                if self.balancer:
                    if status == HealthStatus.HEALTHY:
                        self.balancer.mark_healthy(address)
                    else:
                        self.balancer.mark_unhealthy(address)

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        with self._lock:
            total = len(self._backends)
            active = len([b for b in self._backends.values() if b.is_available])
            connections = sum(b.active_connections for b in self._backends.values())
            requests = sum(b.total_requests for b in self._backends.values())
            errors = sum(b.total_errors for b in self._backends.values())

            return {
                "name": self.config.name,
                "total_backends": total,
                "active_backends": active,
                "total_connections": connections,
                "total_requests": requests,
                "total_errors": errors,
                "error_rate": errors / max(requests, 1),
                "backends": {
                    addr: {
                        "status": b.status.name,
                        "health": b.health_status.name,
                        "connections": b.active_connections,
                        "requests": b.total_requests,
                        "errors": b.total_errors,
                        "avg_latency_ms": b.avg_latency_ms,
                    }
                    for addr, b in self._backends.items()
                },
            }

    def __iter__(self) -> Iterator[Backend]:
        """Iterate over backends."""
        with self._lock:
            return iter(list(self._backends.values()))

    def __len__(self) -> int:
        """Get number of backends."""
        return len(self._backends)


__all__ = [
    "BackendPool",
    "Backend",
    "BackendStatus",
    "PoolConfig",
]
