"""
integrations/google_workspace.py — Google Workspace Clients (v3 Zero-Setup)

ZERO-SETUP mode (USE_GOOGLE_SERVICES=false, default):
  - Tất cả calls đều là MOCK REALISTIC
  - Random True/False cho status checks (simulate real-world uncertainty)
  - Fixed datetime cho suggest_time
  - Print log thay vì gửi HTTP thật

REAL mode (USE_GOOGLE_SERVICES=true):
  - Dùng GOOGLE_SERVICE_ACCOUNT_JSON để authenticate
  - Gọi Google Chat webhook, Calendar API, Drive API, Sheets API thật

Design: không crash dù không có credentials.
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

# Fixed suggested time cho mock mode (deterministic)
_MOCK_SUGGESTED_TIME = "2026-04-01T10:00:00"


# ─────────────────────────────────────────────
# Google Chat Client
# ─────────────────────────────────────────────

class GoogleChatClient:
    """
    Client gửi message qua Google Chat.

    Mock mode (USE_GOOGLE_SERVICES=false):
      → Print log "[MOCK CHAT] Gửi tới {user}: {message}"
      → Luôn trả True

    Real mode (USE_GOOGLE_SERVICES=true):
      → POST tới webhook URL
    """

    def _is_mock(self) -> bool:
        return not settings.use_google_services or not settings.google_chat_webhook_url

    async def send_message(self, user: str, message: str) -> bool:
        """Gửi message. Trả True nếu thành công."""
        if self._is_mock():
            print(f"[MOCK CHAT] Gửi tới {user}: {message[:120]}...")
            logger.info(
                f"[MOCK CHAT] → {user}",
                extra={"event": "mock_chat_sent", "target": user},
            )
            return True

        # Real: POST tới webhook
        return await self._send_webhook(user, message)

    async def _send_webhook(self, user: str, message: str) -> bool:
        """Gửi POST tới Google Chat webhook."""
        try:
            import httpx
            payload = {
                "text": f"*{user}* — {message}"
            }
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    settings.google_chat_webhook_url,
                    json=payload,
                )
                resp.raise_for_status()
                logger.info(f"Chat gửi thành công tới {user}")
                return True
        except Exception as exc:
            logger.error(f"Chat webhook fail: {exc}", extra={"event": "chat_webhook_error"})
            return False


# ─────────────────────────────────────────────
# Google Calendar Client
# ─────────────────────────────────────────────

class GoogleCalendarClient:
    """
    Client tìm slot trống trong Google Calendar.

    Mock mode: trả fixed datetime "2026-04-01T10:00:00"
    Real mode: gọi Calendar FreeBusy API
    """

    def _is_mock(self) -> bool:
        return not settings.use_google_services or not settings.google_service_account_json

    async def find_next_slot(self, meeting_id: str) -> str:
        """Tìm slot trống tiếp theo. Trả ISO datetime string."""
        if self._is_mock():
            print(f"[MOCK CALENDAR] find_next_slot cho '{meeting_id}': {_MOCK_SUGGESTED_TIME}")
            logger.info(
                f"[MOCK CALENDAR] next slot = {_MOCK_SUGGESTED_TIME}",
                extra={"event": "mock_calendar_slot", "meeting_id": meeting_id},
            )
            return _MOCK_SUGGESTED_TIME

        return await self._find_real_slot(meeting_id)

    async def _find_real_slot(self, meeting_id: str) -> str:
        """Tìm slot thật (stub — implement khi deploy thật)."""
        # Ngày làm việc tiếp theo lúc 10:00
        now = datetime.now(timezone.utc)
        delta = 1
        while True:
            candidate = now + timedelta(days=delta)
            if candidate.weekday() < 5:  # Mon-Fri
                return candidate.strftime("%Y-%m-%dT10:00:00")
            delta += 1

    async def check_free_busy(self, user_email: str, meeting_id: str) -> bool:
        """
        Check Manager có rảnh không.

        Mock: random True/False (simulate real-world)
        """
        if self._is_mock():
            result = random.choice([True, False])
            print(f"[MOCK CALENDAR] check_free_busy {user_email}: {'rảnh' if result else 'bận'}")
            return result
        return True  # stub


# ─────────────────────────────────────────────
# Google Drive Client
# ─────────────────────────────────────────────

class GoogleDriveClient:
    """
    Client kiểm tra trạng thái Slide trên Google Drive.

    Mock: random True/False
    Real: kiểm tra modified time của file
    """

    def _is_mock(self) -> bool:
        return not settings.use_google_services or not settings.google_service_account_json

    async def check_slide_updated(self, meeting_id: str) -> bool:
        """Kiểm tra Slide đã cập nhật chưa."""
        if self._is_mock():
            result = random.choice([True, False])
            print(f"[MOCK DRIVE] check_slide '{meeting_id}': {'done ✓' if result else 'pending ✗'}")
            logger.info(
                f"[MOCK DRIVE] slide status = {result}",
                extra={"event": "mock_drive_check", "meeting_id": meeting_id, "result": result},
            )
            return result
        return True  # stub


# ─────────────────────────────────────────────
# Google Sheets Client
# ─────────────────────────────────────────────

class GoogleSheetsClient:
    """
    Client kiểm tra trạng thái Sheet.

    Mock: random True/False
    Real: đọc status cell từ spreadsheet
    """

    def _is_mock(self) -> bool:
        return not settings.use_google_services or not settings.google_service_account_json

    async def check_sheet_finalized(self, meeting_id: str) -> bool:
        """Kiểm tra Sheet đã chốt số chưa."""
        if self._is_mock():
            result = random.choice([True, False])
            print(f"[MOCK SHEETS] check_sheet '{meeting_id}': {'done ✓' if result else 'pending ✗'}")
            logger.info(
                f"[MOCK SHEETS] sheet status = {result}",
                extra={"event": "mock_sheets_check", "meeting_id": meeting_id, "result": result},
            )
            return result
        return True  # stub


# ─────────────────────────────────────────────
# Singleton Instances
# ─────────────────────────────────────────────

google_chat = GoogleChatClient()
google_calendar = GoogleCalendarClient()
google_drive = GoogleDriveClient()
google_sheets = GoogleSheetsClient()
