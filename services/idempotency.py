"""
services/idempotency.py — Async idempotency cache + per-meeting_id lock

Chiến lược:
- Key: meeting_id
- Nếu đang xử lý → chờ kết quả (không xử lý lại)
- Nếu đã xử lý (cached) → trả về kết quả cached
- TTL-based expiry để tránh memory leak
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Optional, Any

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CachedResult:
    """Kết quả được cache cùng với metadata."""
    data: Any
    cached_at: float  # time.monotonic()
    ttl: float


class AsyncIdempotencyCache:
    """
    Async-safe idempotency cache với per-key locking.

    Đảm bảo:
    - Cùng meeting_id đang xử lý → request sau chờ kết quả
    - meeting_id đã hoàn thành trong TTL → trả về cache
    - TTL hết hạn → xử lý lại
    """

    def __init__(self, ttl_seconds: int = None) -> None:
        self.ttl = ttl_seconds or settings.idempotency_ttl_seconds
        # Cache lưu kết quả: meeting_id → CachedResult
        self._cache: Dict[str, CachedResult] = {}
        # Locks per meeting_id: meeting_id → asyncio.Event
        self._locks: Dict[str, asyncio.Event] = {}
        # Global lock để protect _cache và _locks structures
        self._meta_lock = asyncio.Lock()

    async def get_cached(self, meeting_id: str) -> Optional[Any]:
        """
        Kiểm tra cache. Returns None nếu không có hoặc TTL hết hạn.
        """
        async with self._meta_lock:
            result = self._cache.get(meeting_id)
            if result is None:
                return None

            elapsed = time.monotonic() - result.cached_at
            if elapsed > result.ttl:
                # TTL hết hạn → xóa cache
                del self._cache[meeting_id]
                logger.info(
                    "Cache TTL hết hạn, xóa entry",
                    extra={"event": "cache_expired", "meeting_id": meeting_id},
                )
                return None

            logger.info(
                "Cache hit → trả về kết quả cached",
                extra={
                    "event": "cache_hit",
                    "meeting_id": meeting_id,
                    "cached_age_s": round(elapsed, 2),
                },
            )
            return result.data

    async def is_processing(self, meeting_id: str) -> bool:
        """Kiểm tra meeting_id có đang được xử lý không."""
        async with self._meta_lock:
            event = self._locks.get(meeting_id)
            # Có lock nhưng chưa set → đang xử lý
            return event is not None and not event.is_set()

    async def wait_for_result(
        self, meeting_id: str, timeout: float = None
    ) -> Optional[Any]:
        """
        Chờ meeting_id hiện tại xử lý xong, sau đó trả về cached result.
        Returns None nếu timeout hoặc không tìm thấy.
        """
        timeout = timeout or settings.request_timeout_seconds

        async with self._meta_lock:
            event = self._locks.get(meeting_id)

        if event is None:
            return None

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "Timeout khi chờ meeting_id khác xử lý xong",
                extra={"event": "wait_timeout", "meeting_id": meeting_id},
            )
            return None

        return await self.get_cached(meeting_id)

    async def acquire_lock(self, meeting_id: str) -> bool:
        """
        Thử acquire lock cho meeting_id.

        Returns:
            True  → thành công, caller phải gọi release_lock sau khi xong
            False → đang có request khác xử lý
        """
        async with self._meta_lock:
            if meeting_id in self._locks and not self._locks[meeting_id].is_set():
                # Đang xử lý, không acquire được
                return False

            # Tạo event mới, chưa set → đánh dấu "đang xử lý"
            self._locks[meeting_id] = asyncio.Event()
            return True

    async def release_lock(self, meeting_id: str, result: Any) -> None:
        """
        Lưu kết quả vào cache và release lock (set event để notify waiters).
        """
        async with self._meta_lock:
            self._cache[meeting_id] = CachedResult(
                data=result,
                cached_at=time.monotonic(),
                ttl=self.ttl,
            )
            event = self._locks.get(meeting_id)
            if event is not None:
                event.set()  # Notify tất cả waiter

        logger.info(
            "Kết quả được cache, lock released",
            extra={
                "event": "cache_stored",
                "meeting_id": meeting_id,
                "ttl_s": self.ttl,
            },
        )

    async def release_lock_on_error(self, meeting_id: str) -> None:
        """
        Release lock khi xảy ra lỗi (không cache kết quả).
        Giải phóng waiter để họ có thể retry.
        """
        async with self._meta_lock:
            event = self._locks.pop(meeting_id, None)
            if event is not None:
                event.set()

        logger.info(
            "Lock released do lỗi (không cache)",
            extra={"event": "lock_released_error", "meeting_id": meeting_id},
        )

    async def cleanup_expired(self) -> int:
        """
        Đồng bộ dọn dẹp entries hết hạn (chạy trong background task nếu cần).
        Returns số entries đã xóa.
        """
        async with self._meta_lock:
            now = time.monotonic()
            expired_keys = [
                k
                for k, v in self._cache.items()
                if now - v.cached_at > v.ttl
            ]
            for k in expired_keys:
                del self._cache[k]
                self._locks.pop(k, None)
            return len(expired_keys)


# Singleton
idempotency_cache = AsyncIdempotencyCache()
