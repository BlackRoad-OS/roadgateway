"""Readiness and Liveness Probes - Kubernetes-style probes.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from roadgateway_core.health.checker import HealthStatus, HealthResult

logger = logging.getLogger(__name__)


@dataclass
class ProbeConfig:
    """Probe configuration."""

    initial_delay: float = 0.0
    period: float = 10.0
    timeout: float = 5.0
    success_threshold: int = 1
    failure_threshold: int = 3


class ReadinessProbe:
    """Readiness probe for traffic acceptance.

    Determines if the gateway is ready to accept traffic.
    Failed readiness = stop sending traffic.
    """

    def __init__(
        self,
        config: Optional[ProbeConfig] = None,
        checks: Optional[List[Callable[[], HealthResult]]] = None,
    ):
        self.config = config or ProbeConfig()
        self._checks = checks or []
        self._ready = False
        self._consecutive_successes = 0
        self._consecutive_failures = 0
        self._last_check_time: float = 0
        self._lock = threading.RLock()

    def add_check(self, check: Callable[[], HealthResult]) -> "ReadinessProbe":
        """Add a readiness check."""
        self._checks.append(check)
        return self

    def check(self) -> bool:
        """Run readiness check."""
        with self._lock:
            if not self._checks:
                self._ready = True
                return True

            all_healthy = True
            for check in self._checks:
                try:
                    result = check()
                    if result.status != HealthStatus.HEALTHY:
                        all_healthy = False
                        break
                except Exception:
                    all_healthy = False
                    break

            if all_healthy:
                self._consecutive_successes += 1
                self._consecutive_failures = 0
                
                if self._consecutive_successes >= self.config.success_threshold:
                    self._ready = True
            else:
                self._consecutive_failures += 1
                self._consecutive_successes = 0
                
                if self._consecutive_failures >= self.config.failure_threshold:
                    self._ready = False

            self._last_check_time = time.time()
            return self._ready

    @property
    def is_ready(self) -> bool:
        """Get readiness status."""
        return self._ready

    def get_status(self) -> Dict[str, Any]:
        """Get probe status."""
        with self._lock:
            return {
                "ready": self._ready,
                "consecutive_successes": self._consecutive_successes,
                "consecutive_failures": self._consecutive_failures,
                "last_check": self._last_check_time,
            }


class LivenessProbe:
    """Liveness probe for process health.

    Determines if the gateway is alive and should continue running.
    Failed liveness = restart the process.
    """

    def __init__(
        self,
        config: Optional[ProbeConfig] = None,
        checks: Optional[List[Callable[[], HealthResult]]] = None,
    ):
        self.config = config or ProbeConfig()
        self._checks = checks or []
        self._alive = True
        self._consecutive_failures = 0
        self._last_check_time: float = 0
        self._lock = threading.RLock()

    def add_check(self, check: Callable[[], HealthResult]) -> "LivenessProbe":
        """Add a liveness check."""
        self._checks.append(check)
        return self

    def check(self) -> bool:
        """Run liveness check."""
        with self._lock:
            if not self._checks:
                self._alive = True
                return True

            all_healthy = True
            for check in self._checks:
                try:
                    result = check()
                    if result.status == HealthStatus.UNHEALTHY:
                        all_healthy = False
                        break
                except Exception:
                    all_healthy = False
                    break

            if all_healthy:
                self._consecutive_failures = 0
                self._alive = True
            else:
                self._consecutive_failures += 1
                
                if self._consecutive_failures >= self.config.failure_threshold:
                    self._alive = False

            self._last_check_time = time.time()
            return self._alive

    @property
    def is_alive(self) -> bool:
        """Get liveness status."""
        return self._alive

    def get_status(self) -> Dict[str, Any]:
        """Get probe status."""
        with self._lock:
            return {
                "alive": self._alive,
                "consecutive_failures": self._consecutive_failures,
                "last_check": self._last_check_time,
            }


class StartupProbe:
    """Startup probe for initialization.

    Determines if the gateway has completed startup.
    Failed startup = don't start liveness/readiness checks yet.
    """

    def __init__(
        self,
        config: Optional[ProbeConfig] = None,
        checks: Optional[List[Callable[[], HealthResult]]] = None,
    ):
        self.config = config or ProbeConfig(
            initial_delay=0,
            period=10,
            failure_threshold=30,
        )
        self._checks = checks or []
        self._started = False
        self._attempts = 0
        self._max_attempts = self.config.failure_threshold
        self._lock = threading.RLock()

    def add_check(self, check: Callable[[], HealthResult]) -> "StartupProbe":
        """Add a startup check."""
        self._checks.append(check)
        return self

    def check(self) -> bool:
        """Run startup check."""
        with self._lock:
            if self._started:
                return True

            if self._attempts >= self._max_attempts:
                return False

            self._attempts += 1

            if not self._checks:
                self._started = True
                return True

            all_healthy = True
            for check in self._checks:
                try:
                    result = check()
                    if result.status != HealthStatus.HEALTHY:
                        all_healthy = False
                        break
                except Exception:
                    all_healthy = False
                    break

            if all_healthy:
                self._started = True

            return self._started

    @property
    def is_started(self) -> bool:
        """Get startup status."""
        return self._started

    def get_status(self) -> Dict[str, Any]:
        """Get probe status."""
        with self._lock:
            return {
                "started": self._started,
                "attempts": self._attempts,
                "max_attempts": self._max_attempts,
            }


__all__ = [
    "ReadinessProbe",
    "LivenessProbe",
    "StartupProbe",
    "ProbeConfig",
]
