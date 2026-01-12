"""Metrics Collector - Gateway metrics collection.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Metric types."""

    COUNTER = auto()
    GAUGE = auto()
    HISTOGRAM = auto()
    SUMMARY = auto()


@dataclass
class MetricLabels:
    """Metric labels."""

    labels: Dict[str, str] = field(default_factory=dict)

    def to_key(self) -> str:
        """Convert to hashable key."""
        if not self.labels:
            return ""
        return ",".join(f"{k}={v}" for k, v in sorted(self.labels.items()))


class Metric:
    """Base metric class."""

    def __init__(
        self,
        name: str,
        description: str = "",
        labels: Optional[List[str]] = None,
    ):
        self.name = name
        self.description = description
        self.label_names = labels or []
        self._lock = threading.RLock()


class Counter(Metric):
    """Counter metric - monotonically increasing value."""

    def __init__(
        self,
        name: str,
        description: str = "",
        labels: Optional[List[str]] = None,
    ):
        super().__init__(name, description, labels)
        self._values: Dict[str, float] = {}

    def inc(self, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Increment counter."""
        key = MetricLabels(labels or {}).to_key()
        with self._lock:
            self._values[key] = self._values.get(key, 0) + value

    def get(self, labels: Optional[Dict[str, str]] = None) -> float:
        """Get counter value."""
        key = MetricLabels(labels or {}).to_key()
        with self._lock:
            return self._values.get(key, 0)

    def get_all(self) -> Dict[str, float]:
        """Get all counter values."""
        with self._lock:
            return self._values.copy()


class Gauge(Metric):
    """Gauge metric - value that can go up or down."""

    def __init__(
        self,
        name: str,
        description: str = "",
        labels: Optional[List[str]] = None,
    ):
        super().__init__(name, description, labels)
        self._values: Dict[str, float] = {}

    def set(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Set gauge value."""
        key = MetricLabels(labels or {}).to_key()
        with self._lock:
            self._values[key] = value

    def inc(self, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Increment gauge."""
        key = MetricLabels(labels or {}).to_key()
        with self._lock:
            self._values[key] = self._values.get(key, 0) + value

    def dec(self, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Decrement gauge."""
        key = MetricLabels(labels or {}).to_key()
        with self._lock:
            self._values[key] = self._values.get(key, 0) - value

    def get(self, labels: Optional[Dict[str, str]] = None) -> float:
        """Get gauge value."""
        key = MetricLabels(labels or {}).to_key()
        with self._lock:
            return self._values.get(key, 0)

    def get_all(self) -> Dict[str, float]:
        """Get all gauge values."""
        with self._lock:
            return self._values.copy()


class Histogram(Metric):
    """Histogram metric - distribution of values."""

    DEFAULT_BUCKETS = (
        0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75,
        1.0, 2.5, 5.0, 7.5, 10.0, float("inf"),
    )

    def __init__(
        self,
        name: str,
        description: str = "",
        labels: Optional[List[str]] = None,
        buckets: Optional[Tuple[float, ...]] = None,
    ):
        super().__init__(name, description, labels)
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self._counts: Dict[str, Dict[float, int]] = {}
        self._sums: Dict[str, float] = {}
        self._totals: Dict[str, int] = {}

    def observe(
        self,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Observe a value."""
        key = MetricLabels(labels or {}).to_key()
        
        with self._lock:
            if key not in self._counts:
                self._counts[key] = {b: 0 for b in self.buckets}
                self._sums[key] = 0
                self._totals[key] = 0

            self._sums[key] += value
            self._totals[key] += 1

            for bucket in self.buckets:
                if value <= bucket:
                    self._counts[key][bucket] += 1

    def get_buckets(
        self,
        labels: Optional[Dict[str, str]] = None,
    ) -> Dict[float, int]:
        """Get bucket counts."""
        key = MetricLabels(labels or {}).to_key()
        with self._lock:
            return self._counts.get(key, {}).copy()

    def get_sum(self, labels: Optional[Dict[str, str]] = None) -> float:
        """Get sum of observations."""
        key = MetricLabels(labels or {}).to_key()
        with self._lock:
            return self._sums.get(key, 0)

    def get_count(self, labels: Optional[Dict[str, str]] = None) -> int:
        """Get count of observations."""
        key = MetricLabels(labels or {}).to_key()
        with self._lock:
            return self._totals.get(key, 0)


class Summary(Metric):
    """Summary metric - calculates quantiles."""

    def __init__(
        self,
        name: str,
        description: str = "",
        labels: Optional[List[str]] = None,
        quantiles: Optional[Tuple[float, ...]] = None,
        max_age: float = 60.0,
    ):
        super().__init__(name, description, labels)
        self.quantiles = quantiles or (0.5, 0.9, 0.99)
        self.max_age = max_age
        self._observations: Dict[str, List[Tuple[float, float]]] = {}

    def observe(
        self,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Observe a value."""
        key = MetricLabels(labels or {}).to_key()
        now = time.time()

        with self._lock:
            if key not in self._observations:
                self._observations[key] = []

            self._observations[key].append((now, value))
            self._cleanup(key, now)

    def get_quantiles(
        self,
        labels: Optional[Dict[str, str]] = None,
    ) -> Dict[float, float]:
        """Get quantile values."""
        key = MetricLabels(labels or {}).to_key()
        now = time.time()

        with self._lock:
            self._cleanup(key, now)
            
            obs = self._observations.get(key, [])
            if not obs:
                return {q: 0 for q in self.quantiles}

            values = sorted(v for _, v in obs)
            n = len(values)

            return {
                q: values[min(int(q * n), n - 1)]
                for q in self.quantiles
            }

    def get_count(self, labels: Optional[Dict[str, str]] = None) -> int:
        """Get count of observations."""
        key = MetricLabels(labels or {}).to_key()
        with self._lock:
            return len(self._observations.get(key, []))

    def _cleanup(self, key: str, now: float) -> None:
        """Remove old observations."""
        cutoff = now - self.max_age
        if key in self._observations:
            self._observations[key] = [
                (t, v) for t, v in self._observations[key] if t > cutoff
            ]


class MetricsCollector:
    """Metrics collector for the gateway.

    Features:
    - Counter, Gauge, Histogram, Summary metrics
    - Label support
    - Thread-safe
    - Export to Prometheus/JSON

    Architecture:
    ┌────────────────────────────────────────────────────────────┐
    │                   Metrics Collector                         │
    ├────────────────────────────────────────────────────────────┤
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
    │  │   Counters   │  │    Gauges    │  │  Histograms  │     │
    │  │              │  │              │  │              │     │
    │  │ - requests   │  │ - active     │  │ - latency    │     │
    │  │ - errors     │  │   connections│  │ - sizes      │     │
    │  └──────────────┘  └──────────────┘  └──────────────┘     │
    │                                                             │
    │  ┌─────────────────────────────────────────────────────┐   │
    │  │                    Exporters                         │   │
    │  │  - Prometheus format                                 │   │
    │  │  - JSON format                                       │   │
    │  └─────────────────────────────────────────────────────┘   │
    └────────────────────────────────────────────────────────────┘
    """

    def __init__(self, prefix: str = "gateway"):
        self.prefix = prefix
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._summaries: Dict[str, Summary] = {}
        self._lock = threading.RLock()

    def counter(
        self,
        name: str,
        description: str = "",
        labels: Optional[List[str]] = None,
    ) -> Counter:
        """Get or create a counter."""
        full_name = f"{self.prefix}_{name}"
        with self._lock:
            if full_name not in self._counters:
                self._counters[full_name] = Counter(full_name, description, labels)
            return self._counters[full_name]

    def gauge(
        self,
        name: str,
        description: str = "",
        labels: Optional[List[str]] = None,
    ) -> Gauge:
        """Get or create a gauge."""
        full_name = f"{self.prefix}_{name}"
        with self._lock:
            if full_name not in self._gauges:
                self._gauges[full_name] = Gauge(full_name, description, labels)
            return self._gauges[full_name]

    def histogram(
        self,
        name: str,
        description: str = "",
        labels: Optional[List[str]] = None,
        buckets: Optional[Tuple[float, ...]] = None,
    ) -> Histogram:
        """Get or create a histogram."""
        full_name = f"{self.prefix}_{name}"
        with self._lock:
            if full_name not in self._histograms:
                self._histograms[full_name] = Histogram(
                    full_name, description, labels, buckets
                )
            return self._histograms[full_name]

    def summary(
        self,
        name: str,
        description: str = "",
        labels: Optional[List[str]] = None,
        quantiles: Optional[Tuple[float, ...]] = None,
    ) -> Summary:
        """Get or create a summary."""
        full_name = f"{self.prefix}_{name}"
        with self._lock:
            if full_name not in self._summaries:
                self._summaries[full_name] = Summary(
                    full_name, description, labels, quantiles
                )
            return self._summaries[full_name]

    def to_dict(self) -> Dict[str, Any]:
        """Export all metrics as dictionary."""
        result = {
            "counters": {},
            "gauges": {},
            "histograms": {},
            "summaries": {},
        }

        with self._lock:
            for name, counter in self._counters.items():
                result["counters"][name] = counter.get_all()

            for name, gauge in self._gauges.items():
                result["gauges"][name] = gauge.get_all()

            for name, histogram in self._histograms.items():
                result["histograms"][name] = {
                    "buckets": histogram.get_buckets(),
                    "sum": histogram.get_sum(),
                    "count": histogram.get_count(),
                }

            for name, summary in self._summaries.items():
                result["summaries"][name] = {
                    "quantiles": summary.get_quantiles(),
                    "count": summary.get_count(),
                }

        return result


# Default gateway metrics
def create_gateway_metrics(collector: MetricsCollector) -> Dict[str, Metric]:
    """Create standard gateway metrics."""
    return {
        "requests_total": collector.counter(
            "requests_total",
            "Total number of requests",
            ["method", "path", "status"],
        ),
        "request_duration_seconds": collector.histogram(
            "request_duration_seconds",
            "Request duration in seconds",
            ["method", "path"],
        ),
        "active_connections": collector.gauge(
            "active_connections",
            "Number of active connections",
        ),
        "request_size_bytes": collector.histogram(
            "request_size_bytes",
            "Request size in bytes",
            buckets=(100, 1000, 10000, 100000, 1000000, float("inf")),
        ),
        "response_size_bytes": collector.histogram(
            "response_size_bytes",
            "Response size in bytes",
            buckets=(100, 1000, 10000, 100000, 1000000, float("inf")),
        ),
        "errors_total": collector.counter(
            "errors_total",
            "Total number of errors",
            ["type"],
        ),
        "backend_requests_total": collector.counter(
            "backend_requests_total",
            "Total backend requests",
            ["backend", "status"],
        ),
        "backend_latency_seconds": collector.histogram(
            "backend_latency_seconds",
            "Backend latency in seconds",
            ["backend"],
        ),
    }


__all__ = [
    "MetricsCollector",
    "Counter",
    "Gauge",
    "Histogram",
    "Summary",
    "MetricType",
    "MetricLabels",
    "create_gateway_metrics",
]
