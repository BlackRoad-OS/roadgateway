"""Metrics Exporter - Export metrics in various formats.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from roadgateway_core.metrics.collector import (
    MetricsCollector,
    Counter,
    Gauge,
    Histogram,
    Summary,
)

logger = logging.getLogger(__name__)


class MetricsExporter(ABC):
    """Abstract metrics exporter."""

    @abstractmethod
    def export(self, collector: MetricsCollector) -> str:
        """Export metrics to string format."""
        pass


class PrometheusExporter(MetricsExporter):
    """Export metrics in Prometheus format."""

    def export(self, collector: MetricsCollector) -> str:
        """Export to Prometheus text format."""
        lines = []

        # Export counters
        for name, counter in collector._counters.items():
            lines.append(f"# HELP {name} {counter.description}")
            lines.append(f"# TYPE {name} counter")
            
            values = counter.get_all()
            if not values:
                lines.append(f"{name} 0")
            else:
                for labels_key, value in values.items():
                    if labels_key:
                        lines.append(f"{name}{{{labels_key}}} {value}")
                    else:
                        lines.append(f"{name} {value}")

        # Export gauges
        for name, gauge in collector._gauges.items():
            lines.append(f"# HELP {name} {gauge.description}")
            lines.append(f"# TYPE {name} gauge")
            
            values = gauge.get_all()
            if not values:
                lines.append(f"{name} 0")
            else:
                for labels_key, value in values.items():
                    if labels_key:
                        lines.append(f"{name}{{{labels_key}}} {value}")
                    else:
                        lines.append(f"{name} {value}")

        # Export histograms
        for name, histogram in collector._histograms.items():
            lines.append(f"# HELP {name} {histogram.description}")
            lines.append(f"# TYPE {name} histogram")
            
            buckets = histogram.get_buckets()
            cumulative = 0
            for bucket, count in sorted(buckets.items()):
                cumulative += count
                if bucket == float("inf"):
                    lines.append(f'{name}_bucket{{le="+Inf"}} {cumulative}')
                else:
                    lines.append(f'{name}_bucket{{le="{bucket}"}} {cumulative}')
            
            lines.append(f"{name}_sum {histogram.get_sum()}")
            lines.append(f"{name}_count {histogram.get_count()}")

        # Export summaries
        for name, summary in collector._summaries.items():
            lines.append(f"# HELP {name} {summary.description}")
            lines.append(f"# TYPE {name} summary")
            
            quantiles = summary.get_quantiles()
            for quantile, value in quantiles.items():
                lines.append(f'{name}{{quantile="{quantile}"}} {value}')
            
            lines.append(f"{name}_count {summary.get_count()}")

        return "\n".join(lines)


class JSONExporter(MetricsExporter):
    """Export metrics in JSON format."""

    def export(self, collector: MetricsCollector) -> str:
        """Export to JSON format."""
        data = {
            "timestamp": time.time(),
            "metrics": collector.to_dict(),
        }
        return json.dumps(data, indent=2)


class OpenMetricsExporter(MetricsExporter):
    """Export metrics in OpenMetrics format."""

    def export(self, collector: MetricsCollector) -> str:
        """Export to OpenMetrics format."""
        lines = []

        # Similar to Prometheus but with OpenMetrics extensions
        for name, counter in collector._counters.items():
            lines.append(f"# HELP {name} {counter.description}")
            lines.append(f"# TYPE {name} counter")
            
            values = counter.get_all()
            for labels_key, value in values.items():
                if labels_key:
                    lines.append(f"{name}_total{{{labels_key}}} {value}")
                else:
                    lines.append(f"{name}_total {value}")

        # Add EOF marker
        lines.append("# EOF")
        return "\n".join(lines)


class StatsDExporter(MetricsExporter):
    """Export metrics in StatsD format."""

    def export(self, collector: MetricsCollector) -> str:
        """Export to StatsD format."""
        lines = []

        for name, counter in collector._counters.items():
            values = counter.get_all()
            for labels_key, value in values.items():
                metric_name = f"{name}.{labels_key}" if labels_key else name
                lines.append(f"{metric_name}:{value}|c")

        for name, gauge in collector._gauges.items():
            values = gauge.get_all()
            for labels_key, value in values.items():
                metric_name = f"{name}.{labels_key}" if labels_key else name
                lines.append(f"{metric_name}:{value}|g")

        for name, histogram in collector._histograms.items():
            lines.append(f"{name}.sum:{histogram.get_sum()}|g")
            lines.append(f"{name}.count:{histogram.get_count()}|g")

        return "\n".join(lines)


__all__ = [
    "MetricsExporter",
    "PrometheusExporter",
    "JSONExporter",
    "OpenMetricsExporter",
    "StatsDExporter",
]
