"""
services/rate_limiter.py — In-memory sliding window rate limiter

Chiến lược:
- Per-IP sliding window
- Thread-safe với Lock
- Tự động dọn dẹp entries cũ
"""

import time
import threading
from collections import deque
from typing import Dict, Deque

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """
    In-memory sliding window rate limiter.

    Mỗi IP được phép tối đa `max_requests` requests trong `window_seconds`.
    """

    def __init__(
        self,
        max_requests: int = None,
        window_seconds: int = None,
    ) -> None:
        self.max_requests = max_requests or settings.rate_limit_max_requests
        self.window_seconds = window_seconds or settings.rate_limit_window_seconds
        self._lock = threading.Lock()
        # client_id -> deque của timestamps
        self._windows: Dict[str, Deque[float]] = {}

    def is_allowed(self, client_id: str) -> bool:
        """
        Kiểm tra request từ client_id có được phép không.

        Returns:
            True  → cho phép
            False → quá giới hạn
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            if client_id not in self._windows:
                self._windows[client_id] = deque()

            window = self._windows[client_id]

            # Loại bỏ timestamps cũ ngoài window
            while window and window[0] < cutoff:
                window.popleft()

            if len(window) >= self.max_requests:
                logger.warning(
                    "Rate limit vượt ngưỡng",
                    extra={
                        "event": "rate_limit_exceeded",
                        "client_id": client_id,
                        "request_count": len(window),
                        "max_requests": self.max_requests,
                        "window_seconds": self.window_seconds,
                    },
                )
                return False

            window.append(now)
            return True

    def get_remaining(self, client_id: str) -> int:
        """Trả về số requests còn lại trong window hiện tại."""
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            if client_id not in self._windows:
                return self.max_requests

            window = self._windows[client_id]
            active_count = sum(1 for ts in window if ts >= cutoff)
            return max(0, self.max_requests - active_count)

    def cleanup(self) -> None:
        """Dọn dẹp các entries hết hạn (gọi định kỳ nếu cần)."""
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            to_delete = []
            for client_id, window in self._windows.items():
                while window and window[0] < cutoff:
                    window.popleft()
                if not window:
                    to_delete.append(client_id)

            for client_id in to_delete:
                del self._windows[client_id]


# Singleton rate limiter
rate_limiter = RateLimiter()
