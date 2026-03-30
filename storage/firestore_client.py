"""
storage/firestore_client.py — Firestore Client (v3 Zero-Setup)

USE_FIREBASE=false (default): In-memory dict — ZERO-SETUP, không cần Firebase
USE_FIREBASE=true: Kết nối Firebase Firestore thật

In-memory store hoạt động như Firestore về interface,
đủ cho dev, hackathon, demo.
"""

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


class MeetingStateStatus(str, Enum):
    PENDING    = "Pending"
    PROCESSING = "Processing"
    READY      = "Ready"
    UNSAT      = "Unsat"


# ─────────────────────────────────────────────
# In-Memory Store (Zero-Setup)
# ─────────────────────────────────────────────

class MockFirestore:
    """
    In-memory Firestore compatible client.

    Thread-safe cho single-process async workloads.
    Dữ liệu mất khi restart — OK cho dev/test/hackathon.
    """

    def __init__(self):
        # { meeting_id: { lifecycle_status, facts, result, updated_at } }
        self._store: Dict[str, Dict[str, Any]] = {}
        logger.info(
            "MockFirestore initialized (in-memory)",
            extra={"event": "mock_firestore_init"},
        )

    async def get_fact(
        self,
        meeting_id: str,
        fact_key: str,
        default: bool = False,
    ) -> bool:
        """Lấy một fact value cho meeting."""
        meeting = self._store.get(meeting_id, {})
        facts = meeting.get("facts", {})
        return bool(facts.get(fact_key, default))

    async def set_facts(
        self,
        meeting_id: str,
        facts: Dict[str, bool],
    ) -> None:
        """Set nhiều facts cùng lúc."""
        if meeting_id not in self._store:
            self._store[meeting_id] = {}
        self._store[meeting_id]["facts"] = facts
        self._store[meeting_id]["updated_at"] = datetime.now(timezone.utc).isoformat()

    async def update_meeting_status(
        self,
        meeting_id: str,
        status: MeetingStateStatus,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Cập nhật lifecycle status của meeting."""
        if meeting_id not in self._store:
            self._store[meeting_id] = {}
        self._store[meeting_id]["lifecycle_status"] = status.value
        self._store[meeting_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
        if result:
            self._store[meeting_id]["result"] = result
        logger.debug(
            f"MockFirestore: {meeting_id} → {status.value}",
            extra={"event": "mock_firestore_update", "meeting_id": meeting_id, "status": status.value},
        )

    async def get_meeting_status(
        self,
        meeting_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Lấy toàn bộ state của meeting. None nếu chưa có."""
        return self._store.get(meeting_id)

    async def delete_meeting(self, meeting_id: str) -> None:
        """Xóa meeting khỏi store."""
        self._store.pop(meeting_id, None)


# ─────────────────────────────────────────────
# Real Firestore Client
# ─────────────────────────────────────────────

class RealFirestoreClient:
    """
    Firebase Firestore client thật.
    Chỉ khởi tạo khi USE_FIREBASE=true.
    """

    def __init__(self):
        self._client = None
        self._collection = "meetings"
        logger.info(
            "RealFirestoreClient: khởi tạo...",
            extra={"event": "firestore_init_start"},
        )
        try:
            self._client = self._build_client()
            logger.info(
                "Firestore connected",
                extra={"event": "firestore_connected", "project": settings.firebase_project_id},
            )
        except Exception as exc:
            logger.error(
                f"Firestore init fail — sẽ dùng MockFirestore: {exc}",
                extra={"event": "firestore_init_fail"},
            )
            self._client = None

    def _build_client(self):
        """Khởi tạo Firestore client từ service account."""
        import google.auth
        from google.cloud import firestore as _fs

        sa_json = settings.google_service_account_json
        project = settings.firebase_project_id

        if not project:
            raise ValueError("FIREBASE_PROJECT_ID chưa được set")

        if sa_json:
            import json
            import os
            from google.oauth2 import service_account

            # JSON string hoặc file path
            if sa_json.strip().startswith("{"):
                creds_dict = json.loads(sa_json)
            elif os.path.isfile(sa_json):
                with open(sa_json) as f:
                    creds_dict = json.load(f)
            else:
                raise ValueError(f"GOOGLE_SERVICE_ACCOUNT_JSON không hợp lệ: {sa_json[:50]}")

            credentials = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            return _fs.AsyncClient(project=project, credentials=credentials)
        else:
            return _fs.AsyncClient(project=project)

    async def _doc_ref(self, meeting_id: str):
        return self._client.collection(self._collection).document(meeting_id)

    async def get_fact(self, meeting_id: str, fact_key: str, default: bool = False) -> bool:
        if not self._client:
            return default
        try:
            doc = await (await self._doc_ref(meeting_id)).get()
            if doc.exists:
                facts = doc.to_dict().get("facts", {})
                return bool(facts.get(fact_key, default))
        except Exception as exc:
            logger.warning(f"Firestore get_fact fail: {exc}")
        return default

    async def set_facts(self, meeting_id: str, facts: Dict[str, bool]) -> None:
        if not self._client:
            return
        try:
            ref = await self._doc_ref(meeting_id)
            await ref.set({"facts": facts, "updated_at": datetime.now(timezone.utc).isoformat()}, merge=True)
        except Exception as exc:
            logger.warning(f"Firestore set_facts fail: {exc}")

    async def update_meeting_status(
        self,
        meeting_id: str,
        status: MeetingStateStatus,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self._client:
            return
        try:
            ref = await self._doc_ref(meeting_id)
            data = {
                "lifecycle_status": status.value,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if result:
                data["result"] = result
            await ref.set(data, merge=True)
        except Exception as exc:
            logger.warning(f"Firestore update_status fail: {exc}")

    async def get_meeting_status(self, meeting_id: str) -> Optional[Dict[str, Any]]:
        if not self._client:
            return None
        try:
            doc = await (await self._doc_ref(meeting_id)).get()
            if doc.exists:
                return doc.to_dict()
        except Exception as exc:
            logger.warning(f"Firestore get_status fail: {exc}")
        return None

    async def delete_meeting(self, meeting_id: str) -> None:
        if not self._client:
            return
        try:
            ref = await self._doc_ref(meeting_id)
            await ref.delete()
        except Exception as exc:
            logger.warning(f"Firestore delete fail: {exc}")


# ─────────────────────────────────────────────
# Factory — Auto-select based on config
# ─────────────────────────────────────────────

def _create_client():
    """
    Tự động chọn client dựa vào USE_FIREBASE setting.

    USE_FIREBASE=false (default) → MockFirestore (zero-setup)
    USE_FIREBASE=true → RealFirestoreClient → fallback MockFirestore nếu fail
    """
    if not settings.use_firebase:
        logger.info(
            "USE_FIREBASE=false → dùng MockFirestore (in-memory)",
            extra={"event": "storage_mock_mode"},
        )
        return MockFirestore()

    # Thử kết nối Firestore thật
    client = RealFirestoreClient()
    if client._client is None:
        logger.warning(
            "Firestore không khởi động được → fallback MockFirestore",
            extra={"event": "storage_fallback_mock"},
        )
        return MockFirestore()

    return client


# Singleton
firestore_client = _create_client()
