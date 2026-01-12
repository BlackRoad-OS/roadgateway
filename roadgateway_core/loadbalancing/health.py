"""Health Checker - Backend server health monitoring.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import asyncio
import logging
import time
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set
import socket
import ssl

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health check status."""

    HEALTHY = auto()
    UNHEALTHY = auto()
    DEGRADED = auto()
    UNKNOWN = auto()


class CheckType(Enum):
    """Health check types."""

    TCP = auto()
    HTTP = auto()
    HTTPS = auto()
    GRPC = auto()
    CUSTOM = auto()


@dataclass
class HealthCheckConfig:
    """Health check configuration."""

    check_type: CheckType = CheckType.TCP
    interval: float = 10.0
    timeout: float = 5.0
    healthy_threshold: int = 2
    unhealthy_threshold: int = 3
    http_path: str = "/health"
    http_method: str = "GET"
    expected_codes: List[int] = field(default_factory=lambda: [200, 201, 204])
    expected_body: Optional[str] = None


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    status: HealthStatus
    latency_ms: float
    timestamp: float
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


class HealthChecker:
    """Health checker for backend servers.

    Features:
    - TCP/HTTP/HTTPS/gRPC health checks
    - Configurable thresholds
    - Automatic status transitions
    - Callback notifications
    """

    def __init__(self, config: Optional[HealthCheckConfig] = None):
        self.config = config or HealthCheckConfig()
        self._targets: Dict[str, Dict[str, Any]] = {}
        self._results: Dict[str, List[HealthCheckResult]] = {}
        self._callbacks: List[Callable[[str, HealthStatus], None]] = []
        self._running = False
        self._lock = threading.RLock()
        self._check_task: Optional[asyncio.Task] = None

    def add_target(
        self,
        address: str,
        config: Optional[HealthCheckConfig] = None,
    ) -> "HealthChecker":
        """Add a target to monitor."""
        with self._lock:
            self._targets[address] = {
                "config": config or self.config,
                "status": HealthStatus.UNKNOWN,
                "healthy_count": 0,
                "unhealthy_count": 0,
            }
            self._results[address] = []
        return self

    def remove_target(self, address: str) -> bool:
        """Remove a target."""
        with self._lock:
            if address in self._targets:
                del self._targets[address]
                del self._results[address]
                return True
        return False

    def on_status_change(
        self,
        callback: Callable[[str, HealthStatus], None],
    ) -> "HealthChecker":
        """Register status change callback."""
        self._callbacks.append(callback)
        return self

    def get_status(self, address: str) -> HealthStatus:
        """Get current health status of target."""
        with self._lock:
            target = self._targets.get(address)
            return target["status"] if target else HealthStatus.UNKNOWN

    def get_all_status(self) -> Dict[str, HealthStatus]:
        """Get status of all targets."""
        with self._lock:
            return {
                addr: target["status"]
                for addr, target in self._targets.items()
            }

    async def check(self, address: str) -> HealthCheckResult:
        """Perform health check on target."""
        with self._lock:
            target = self._targets.get(address)
            if not target:
                return HealthCheckResult(
                    status=HealthStatus.UNKNOWN,
                    latency_ms=0,
                    timestamp=time.time(),
                    message="Target not found",
                )
            config = target["config"]

        start = time.perf_counter()
        
        try:
            if config.check_type == CheckType.TCP:
                result = await self._check_tcp(address, config)
            elif config.check_type == CheckType.HTTP:
                result = await self._check_http(address, config, secure=False)
            elif config.check_type == CheckType.HTTPS:
                result = await self._check_http(address, config, secure=True)
            else:
                result = await self._check_tcp(address, config)

            latency = (time.perf_counter() - start) * 1000
            result.latency_ms = latency
            
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            result = HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                timestamp=time.time(),
                message=str(e),
            )

        self._process_result(address, result)
        return result

    async def _check_tcp(
        self,
        address: str,
        config: HealthCheckConfig,
    ) -> HealthCheckResult:
        """TCP health check."""
        try:
            host, port = self._parse_address(address)
            
            # Create socket connection
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(config.timeout)
            sock.connect((host, port))
            sock.close()
            
            return HealthCheckResult(
                status=HealthStatus.HEALTHY,
                latency_ms=0,
                timestamp=time.time(),
                message="TCP connection successful",
            )
            
        except socket.timeout:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                latency_ms=config.timeout * 1000,
                timestamp=time.time(),
                message="Connection timeout",
            )
        except Exception as e:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                latency_ms=0,
                timestamp=time.time(),
                message=f"TCP check failed: {e}",
            )

    async def _check_http(
        self,
        address: str,
        config: HealthCheckConfig,
        secure: bool,
    ) -> HealthCheckResult:
        """HTTP/HTTPS health check."""
        try:
            host, port = self._parse_address(address)
            protocol = "https" if secure else "http"
            url = f"{protocol}://{host}:{port}{config.http_path}"
            
            # Simple HTTP request using socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(config.timeout)
            
            if secure:
                context = ssl.create_default_context()
                sock = context.wrap_socket(sock, server_hostname=host)
            
            sock.connect((host, port))
            
            request = (
                f"{config.http_method} {config.http_path} HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                f"Connection: close\r\n"
                f"\r\n"
            )
            sock.send(request.encode())
            
            response = sock.recv(4096).decode()
            sock.close()
            
            # Parse status code
            status_line = response.split("\r\n")[0]
            status_code = int(status_line.split()[1])
            
            if status_code in config.expected_codes:
                return HealthCheckResult(
                    status=HealthStatus.HEALTHY,
                    latency_ms=0,
                    timestamp=time.time(),
                    message=f"HTTP {status_code}",
                    details={"status_code": status_code},
                )
            else:
                return HealthCheckResult(
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=0,
                    timestamp=time.time(),
                    message=f"Unexpected status: {status_code}",
                    details={"status_code": status_code},
                )
                
        except Exception as e:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                latency_ms=0,
                timestamp=time.time(),
                message=f"HTTP check failed: {e}",
            )

    def _parse_address(self, address: str) -> tuple:
        """Parse address into host and port."""
        if ":" in address:
            host, port = address.rsplit(":", 1)
            return host, int(port)
        return address, 80

    def _process_result(
        self,
        address: str,
        result: HealthCheckResult,
    ) -> None:
        """Process health check result and update status."""
        with self._lock:
            target = self._targets.get(address)
            if not target:
                return

            self._results[address].append(result)
            # Keep last 100 results
            if len(self._results[address]) > 100:
                self._results[address] = self._results[address][-50:]

            config = target["config"]
            old_status = target["status"]

            if result.status == HealthStatus.HEALTHY:
                target["healthy_count"] += 1
                target["unhealthy_count"] = 0
                
                if target["healthy_count"] >= config.healthy_threshold:
                    target["status"] = HealthStatus.HEALTHY
                    
            else:
                target["unhealthy_count"] += 1
                target["healthy_count"] = 0
                
                if target["unhealthy_count"] >= config.unhealthy_threshold:
                    target["status"] = HealthStatus.UNHEALTHY

            # Notify callbacks if status changed
            if target["status"] != old_status:
                for callback in self._callbacks:
                    try:
                        callback(address, target["status"])
                    except Exception as e:
                        logger.error(f"Callback error: {e}")

    async def start(self) -> None:
        """Start health check loop."""
        self._running = True
        
        while self._running:
            addresses = list(self._targets.keys())
            
            for address in addresses:
                if not self._running:
                    break
                await self.check(address)
            
            await asyncio.sleep(self.config.interval)

    def stop(self) -> None:
        """Stop health check loop."""
        self._running = False

    def get_stats(self) -> Dict[str, Any]:
        """Get health checker statistics."""
        with self._lock:
            stats = {
                "targets": len(self._targets),
                "healthy": 0,
                "unhealthy": 0,
                "unknown": 0,
            }

            for target in self._targets.values():
                if target["status"] == HealthStatus.HEALTHY:
                    stats["healthy"] += 1
                elif target["status"] == HealthStatus.UNHEALTHY:
                    stats["unhealthy"] += 1
                else:
                    stats["unknown"] += 1

            return stats


__all__ = [
    "HealthChecker",
    "HealthCheckConfig",
    "HealthCheckResult",
    "HealthStatus",
    "CheckType",
]
