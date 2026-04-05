"""
core/metrics.py — In-memory metrics tracker (counters + per-node latency)

Thiết kế Memory-Bounded:
──────────────────────────────────────────────────────────────
  • latencies: deque(maxlen=1000) — O(1) append & bounded memory.
  • p99: sorted() trên tối đa 1000 phần tử → O(1000 log 1000)
    ≈ constant time, KHÔNG phình to theo traffic.
  • avg: tính từ sum(latencies) / len(latencies) trực tiếp trên
    deque window — chính xác luôn phản ánh 1000 samples gần nhất.

Lý do KHÔNG dùng running `total_latency_ms / call_count` cho avg
của NodeMetrics: khi deque bị cắt (maxlen), tổng tích lũy mãi
trong khi count đã bị mất, dẫn đến avg sai. Ta cộng deque thật.
"""

import threading
import collections
from dataclasses import dataclass, field
from typing import Dict


# ─────────────────────────────────────────────
# Per-Node Metrics
# ─────────────────────────────────────────────

@dataclass
class NodeMetrics:
    """
    Metrics cho một LangGraph node.

    Attributes:
        call_count:       Số lần node được gọi (tổng, bao gồm lỗi).
        error_count:      Số lần node thất bại.
        latencies:        Sliding window 1000 samples gần nhất (ms).
    """
    call_count: int = 0
    error_count: int = 0
    # maxlen=1000: O(1) bounded memory, không phình to.
    latencies: collections.deque = field(
        default_factory=lambda: collections.deque(maxlen=1000)
    )

    @property
    def avg_latency_ms(self) -> float:
        """
        Trung bình latency từ sliding window (1000 samples gần nhất).

        Tính trực tiếp từ deque thay vì từ total_latency_ms để đảm bảo
        chính xác khi deque bị cắt (maxlen eviction).
        """
        if not self.latencies:
            return 0.0
        return sum(self.latencies) / len(self.latencies)

    @property
    def p99_latency_ms(self) -> float:
        """
        Percentile 99 latency từ sliding window.

        Với maxlen=1000: sorted() chạy trên tối đa 1000 phần tử,
        tức O(~10_000 comparisons) — constant time với traffic cao.
        """
        if not self.latencies:
            return 0.0
        sorted_lat = sorted(self.latencies)  # O(n log n), n ≤ 1000
        idx = min(int(len(sorted_lat) * 0.99), len(sorted_lat) - 1)
        return sorted_lat[idx]


# ─────────────────────────────────────────────
# Global Metrics Collector
# ─────────────────────────────────────────────

class MetricsCollector:
    """
    Thread-safe in-memory metrics collector.

    Theo dõi:
    - Tổng requests, success, failure (tất cả thời gian).
    - Per-node latency trong sliding window 1000 samples.

    Thread-Safety: threading.Lock bảo vệ tất cả mutations.
    Không dùng asyncio.Lock để tránh deadlock khi gọi từ
    run_in_executor (thread pool context).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Global counters (tổng tất cả thời gian)
        self.total_requests: int = 0
        self.success_count: int = 0
        self.failure_count: int = 0
        self.total_latency_ms: float = 0.0
        # Per-node metrics
        self._node_metrics: Dict[str, NodeMetrics] = {}

    def record_request(
        self,
        success: bool,
        latency_ms: float,
    ) -> None:
        """
        Ghi nhận một request hoàn thành.

        Args:
            success:    True nếu request kết thúc thành công (HTTP 2xx).
            latency_ms: Thời gian xử lý end-to-end (milliseconds).
        """
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
        """
        Ghi nhận latency của một LangGraph node.

        Args:
            node_name:  Tên node (e.g., "parse_input", "verify_logic").
            latency_ms: Thời gian chạy node (milliseconds).
            error:      True nếu node kết thúc bằng exception.
        """
        with self._lock:
            if node_name not in self._node_metrics:
                self._node_metrics[node_name] = NodeMetrics()
            m = self._node_metrics[node_name]
            m.call_count += 1
            m.latencies.append(latency_ms)  # deque tự cắt khi > maxlen
            if error:
                m.error_count += 1

    def get_summary(self) -> dict:
        """
        Lấy snapshot metrics hiện tại (thread-safe).

        Returns:
            Dict với tổng requests, tỉ lệ thành công, avg latency, và
            per-node stats (call_count, error_count, avg/p99 latency).
        """
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


# ─────────────────────────────────────────────
# Singleton global metrics collector
# ─────────────────────────────────────────────

metrics = MetricsCollector()
