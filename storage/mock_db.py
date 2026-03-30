"""
storage/mock_db.py — In-memory mock Firebase/Firestore

Simulate:
- Meeting facts storage (slide status, sheet status, calendar)
- Thread-safe với threading.Lock
- Async interface để compatible với production Firebase

Structure (per meeting_id):
{
    "Slide_Done": bool,
    "Sheet_Done": bool,
    "Manager_Free": bool,
    ...
}
"""

import asyncio
import random
import threading
import time
from typing import Any, Dict, Optional

from core.logging import get_logger

logger = get_logger(__name__)


class MockFirestore:
    """
    In-memory mock database simulate Firebase Firestore.

    Đặc điểm:
    - Singleton pattern
    - Thread-safe với Lock
    - Async interface
    - Simulate network latency (10-50ms)
    - Pre-seeded với mock data
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # Pre-seeded mock data
        # Structure: meeting_id → facts dict
        self._data: Dict[str, Dict[str, Any]] = {
            "meeting-demo-001": {
                "Slide_Done": False,
                "Sheet_Done": True,
                "Manager_Free": False,
                "Attendees_Confirmed": True,
            },
            "meeting-demo-002": {
                "Slide_Done": True,
                "Sheet_Done": True,
                "Manager_Free": True,
                "Attendees_Confirmed": True,
            },
            "meeting-demo-003": {
                "Slide_Done": False,
                "Sheet_Done": False,
                "Manager_Free": True,
                "Attendees_Confirmed": False,
            },
        }

    async def get_meeting_facts(
        self,
        meeting_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Lấy toàn bộ facts của một cuộc họp.

        Args:
            meeting_id: ID cuộc họp

        Returns:
            Dict facts hoặc None nếu không tìm thấy
        """
        # Simulate async latency
        await asyncio.sleep(random.uniform(0.01, 0.05))

        with self._lock:
            data = self._data.get(meeting_id)
            if data is not None:
                return dict(data)  # Copy để tránh mutation
            return None

    async def get_fact(
        self,
        meeting_id: str,
        fact_key: str,
        default: bool = False,
    ) -> bool:
        """
        Lấy một fact cụ thể của cuộc họp.

        Args:
            meeting_id: ID cuộc họp
            fact_key: Tên fact (e.g., "Slide_Done")
            default: Giá trị mặc định nếu không tìm thấy

        Returns:
            bool value của fact
        """
        await asyncio.sleep(random.uniform(0.01, 0.03))

        with self._lock:
            data = self._data.get(meeting_id)
            if data is None:
                logger.info(
                    f"Meeting '{meeting_id}' không có trong DB, dùng default={default}",
                    extra={
                        "event": "db_miss",
                        "meeting_id": meeting_id,
                        "fact_key": fact_key,
                    },
                )
                return default
            return data.get(fact_key, default)

    async def set_meeting_facts(
        self,
        meeting_id: str,
        facts: Dict[str, Any],
    ) -> None:
        """
        Lưu/cập nhật facts cho một cuộc họp.

        Args:
            meeting_id: ID cuộc họp
            facts: Dict facts cần lưu
        """
        await asyncio.sleep(random.uniform(0.01, 0.05))

        with self._lock:
            if meeting_id not in self._data:
                self._data[meeting_id] = {}
            self._data[meeting_id].update(facts)

        logger.info(
            f"Đã lưu facts cho meeting '{meeting_id}'",
            extra={
                "event": "db_write",
                "meeting_id": meeting_id,
                "keys": list(facts.keys()),
            },
        )

    async def delete_meeting(self, meeting_id: str) -> bool:
        """Xóa meeting khỏi DB. Returns True nếu tìm thấy và xóa."""
        await asyncio.sleep(random.uniform(0.005, 0.02))

        with self._lock:
            if meeting_id in self._data:
                del self._data[meeting_id]
                return True
            return False

    def seed(self, meeting_id: str, facts: Dict[str, Any]) -> None:
        """Seed data đồng bộ (dùng trong tests)."""
        with self._lock:
            self._data[meeting_id] = dict(facts)

    def get_all_meetings(self) -> Dict[str, Dict[str, Any]]:
        """Lấy toàn bộ data (dùng trong debug/tests)."""
        with self._lock:
            return {k: dict(v) for k, v in self._data.items()}


# Singleton
mock_db = MockFirestore()
