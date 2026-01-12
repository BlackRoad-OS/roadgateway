"""Health Checker - Gateway health monitoring.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import asyncio
import logging
import time
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health check status."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass
class HealthResult:
    """Result of a health check."""

    status: HealthStatus
    name: str
    message: str = ""
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthCheck:
    """Health check definition."""

    name: str
    check_func: Callable[[], HealthResult]
    interval: float = 30.0
    timeout: float = 10.0
    critical: bool = True
    tags: List[str] = field(default_factory=list)


class HealthChecker:
    """Gateway Health Checker.

    Features:
    - Multiple health checks
    - Async execution
    - Caching
    - Status aggregation

    Health Check Types:
    ┌────────────────────────────────────────────────────────────┐
    │                    Health Checks                            │
    ├────────────────────────────────────────────────────────────┤
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
    │  │   Backend    │  │   Database   │  │   Cache      │     │
    │  │   Health     │  │   Health     │  │   Health     │     │
    │  └──────────────┘  └──────────────┘  └──────────────┘     │
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
    │  │   Memory     │  │   Disk       │  │   Custom     │     │
    │  │   Health     │  │   Health     │  │   Health     │     │
    │  └──────────────┘  └──────────────┘  └──────────────┘     │
    └────────────────────────────────────────────────────────────┘
    """

    def __init__(self):
        self._checks: Dict[str, HealthCheck] = {}
        self._results: Dict[str, HealthResult] = {}
        self._lock = threading.RLock()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def add_check(self, check: HealthCheck) -> "HealthChecker":
        """Add a health check."""
        with self._lock:
            self._checks[check.name] = check
        return self

    def remove_check(self, name: str) -> bool:
        """Remove a health check."""
        with self._lock:
            if name in self._checks:
                del self._checks[name]
                return True
        return False

    def check(self, name: str) -> HealthResult:
        """Run a specific health check."""
        with self._lock:
            check = self._checks.get(name)
            if not check:
                return HealthResult(
                    status=HealthStatus.UNKNOWN,
                    name=name,
                    message="Check not found",
                )

        start = time.perf_counter()
        try:
            result = check.check_func()
            result.latency_ms = (time.perf_counter() - start) * 1000
        except Exception as e:
            result = HealthResult(
                status=HealthStatus.UNHEALTHY,
                name=name,
                message=str(e),
                latency_ms=(time.perf_counter() - start) * 1000,
            )

        with self._lock:
            self._results[name] = result

        return result

    def check_all(self) -> Dict[str, HealthResult]:
        """Run all health checks."""
        results = {}
        for name in list(self._checks.keys()):
            results[name] = self.check(name)
        return results

    async def check_async(self, name: str) -> HealthResult:
        """Run health check asynchronously."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.check, name
        )

    async def check_all_async(self) -> Dict[str, HealthResult]:
        """Run all checks concurrently."""
        tasks = [
            self.check_async(name)
            for name in self._checks.keys()
        ]
        results = await asyncio.gather(*tasks)
        return {r.name: r for r in results}

    def get_status(self) -> HealthStatus:
        """Get overall health status."""
        with self._lock:
            if not self._results:
                return HealthStatus.UNKNOWN

            has_unhealthy = False
            has_degraded = False

            for name, result in self._results.items():
                check = self._checks.get(name)
                
                if result.status == HealthStatus.UNHEALTHY:
                    if check and check.critical:
                        return HealthStatus.UNHEALTHY
                    has_unhealthy = True
                elif result.status == HealthStatus.DEGRADED:
                    has_degraded = True

            if has_unhealthy or has_degraded:
                return HealthStatus.DEGRADED

            return HealthStatus.HEALTHY

    def get_results(self) -> Dict[str, HealthResult]:
        """Get cached health check results."""
        with self._lock:
            return self._results.copy()

    def get_summary(self) -> Dict[str, Any]:
        """Get health summary."""
        with self._lock:
            status = self.get_status()
            
            healthy = 0
            unhealthy = 0
            degraded = 0
            
            for result in self._results.values():
                if result.status == HealthStatus.HEALTHY:
                    healthy += 1
                elif result.status == HealthStatus.UNHEALTHY:
                    unhealthy += 1
                elif result.status == HealthStatus.DEGRADED:
                    degraded += 1

            return {
                "status": status.value,
                "checks": {
                    "total": len(self._checks),
                    "healthy": healthy,
                    "unhealthy": unhealthy,
                    "degraded": degraded,
                },
                "details": {
                    name: {
                        "status": r.status.value,
                        "message": r.message,
                        "latency_ms": r.latency_ms,
                    }
                    for name, r in self._results.items()
                },
            }

    async def start_periodic_checks(self) -> None:
        """Start periodic health checks."""
        self._running = True

        while self._running:
            await self.check_all_async()
            await asyncio.sleep(30)  # Default interval

    def stop(self) -> None:
        """Stop periodic checks."""
        self._running = False


# Common health check factories
def tcp_check(name: str, host: str, port: int, timeout: float = 5.0) -> HealthCheck:
    """Create TCP health check."""
    import socket

    def check_func() -> HealthResult:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((host, port))
            sock.close()
            return HealthResult(
                status=HealthStatus.HEALTHY,
                name=name,
                message=f"TCP connection to {host}:{port} successful",
            )
        except Exception as e:
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                name=name,
                message=str(e),
            )

    return HealthCheck(name=name, check_func=check_func, timeout=timeout)


def http_check(
    name: str,
    url: str,
    expected_status: int = 200,
    timeout: float = 10.0,
) -> HealthCheck:
    """Create HTTP health check."""
    import urllib.request

    def check_func() -> HealthResult:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                if status == expected_status:
                    return HealthResult(
                        status=HealthStatus.HEALTHY,
                        name=name,
                        message=f"HTTP {status}",
                        details={"url": url, "status_code": status},
                    )
                else:
                    return HealthResult(
                        status=HealthStatus.DEGRADED,
                        name=name,
                        message=f"Unexpected status {status}",
                        details={"url": url, "status_code": status},
                    )
        except Exception as e:
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                name=name,
                message=str(e),
                details={"url": url},
            )

    return HealthCheck(name=name, check_func=check_func, timeout=timeout)


def memory_check(
    name: str = "memory",
    threshold_percent: float = 90.0,
) -> HealthCheck:
    """Create memory usage health check."""
    import os

    def check_func() -> HealthResult:
        try:
            # This is a simplified check
            # In production, use psutil or similar
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            mem_mb = usage.ru_maxrss / 1024  # Convert to MB on most systems
            
            return HealthResult(
                status=HealthStatus.HEALTHY,
                name=name,
                message=f"Memory usage: {mem_mb:.1f}MB",
                details={"memory_mb": mem_mb},
            )
        except Exception as e:
            return HealthResult(
                status=HealthStatus.UNKNOWN,
                name=name,
                message=str(e),
            )

    return HealthCheck(name=name, check_func=check_func, critical=False)


__all__ = [
    "HealthChecker",
    "HealthCheck",
    "HealthResult",
    "HealthStatus",
    "tcp_check",
    "http_check",
    "memory_check",
]
