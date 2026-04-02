"""
core/metrics.py — In-memory metrics tracker (counters + per-node latency)
"""

import time
import threading
import collections
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class NodeMetrics:
    """Metrics cho một LangGraph node."""
    call_count: int = 0
    error_count: int = 0
    total_latency_ms: float = 0.0
    latencies: collections.deque = field(default_factory=lambda: collections.deque(maxlen=1000))

    @property
    def avg_latency_ms(self) -> float:
        if not self.latencies:
            return 0.0
        return self.total_latency_ms / len(self.latencies)

    @property
    def p99_latency_ms(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_lat = sorted(self.latencies)
        idx = int(len(sorted_lat) * 0.99)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]


class MetricsCollector:
    """
    Thread-safe in-memory metrics collector.
    Theo dõi: total requests, success/failure, per-node latency.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.total_requests: int = 0
        self.success_count: int = 0
        self.failure_count: int = 0
        self.total_latency_ms: float = 0.0
        self._node_metrics: Dict[str, NodeMetrics] = {}

    def record_request(
        self,
        success: bool,
        latency_ms: float,
    ) -> None:
        with self._lock:
            self.total_requests += 1
            self.total_latency_ms += latency_ms
            if success:
                self.success_count += 1
            else:
                self.failure_count += 1

    def record_node(
        self,
        node_name: str,
        latency_ms: float,
        error: bool = False,
    ) -> None:
        with self._lock:
            if node_name not in self._node_metrics:
                self._node_metrics[node_name] = NodeMetrics()
            m = self._node_metrics[node_name]
            m.call_count += 1
            m.total_latency_ms += latency_ms
            m.latencies.append(latency_ms)
            if error:
                m.error_count += 1

    def get_summary(self) -> dict:
        with self._lock:
            return {
                "total_requests": self.total_requests,
                "success_count": self.success_count,
                "failure_count": self.failure_count,
                "avg_total_latency_ms": (
                    round(self.total_latency_ms / self.total_requests, 2)
                    if self.total_requests > 0
                    else 0.0
                ),
                "nodes": {
                    name: {
                        "call_count": m.call_count,
                        "error_count": m.error_count,
                        "avg_latency_ms": round(m.avg_latency_ms, 2),
                        "p99_latency_ms": round(m.p99_latency_ms, 2),
                    }
                    for name, m in self._node_metrics.items()
                },
            }


# Singleton global metrics collector
metrics = MetricsCollector()
