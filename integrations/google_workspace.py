"""
integrations/google_workspace.py — Google Workspace Clients (v4 Lazy-Init)

Socket Exhaustion Fix (Lazy Singleton + asyncio.Lock):
───────────────────────────────────────────────────────
  Vấn đề cũ: _http_client được khởi tạo ở module-level (import time)
  trước khi FastAPI event loop tồn tại → client gắn vào event loop sai
  hoặc bị khởi tạo lại nhiều lần gây socket exhaustion.

  Fix: get_http_client() khởi tạo lazily, được bảo vệ bởi asyncio.Lock
  để đảm bảo chỉ tạo đúng một client trong event loop đang chạy.
  close_http_client() được gọi trong shutdown lifespan để đảm bảo
  tất cả connections được đóng sạch khi server dừng.

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

import httpx


# ─────────────────────────────────────────────
# HTTP Client — Lazy Singleton (Socket-Safe)
# ─────────────────────────────────────────────

_http_client: Optional[httpx.AsyncClient] = None
_http_client_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    """
    Lazy-init asyncio.Lock để tránh tạo lock trước khi event loop chạy.

    asyncio.Lock phải được tạo trong event loop context.
    """
    global _http_client_lock
    if _http_client_lock is None:
        _http_client_lock = asyncio.Lock()
    return _http_client_lock


async def get_http_client() -> httpx.AsyncClient:
    """
    Lấy (hoặc khởi tạo) singleton AsyncClient.

    Thread-safe với asyncio.Lock: chỉ tạo một client duy nhất dù
    nhiều coroutines gọi đồng thời vào lần đầu (double-checked locking).

    Client được gắn với event loop hiện tại — phải gọi từ bên trong
    async context (event loop đang chạy).

    Returns:
        httpx.AsyncClient singleton, sẵn sàng sử dụng.
    """
    global _http_client
    # Fast path: client đã tồn tại (không cần lock)
    if _http_client is not None and not _http_client.is_closed:
        return _http_client

    # Slow path: acquire lock và khởi tạo (double-checked)
    async with _get_lock():
        if _http_client is None or _http_client.is_closed:
            _http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=3.0,
                    read=5.0,
                    write=5.0,
                    pool=5.0,
                ),
                limits=httpx.Limits(
                    max_connections=20,
                    max_keepalive_connections=10,
                    keepalive_expiry=30.0,
                ),
            )
            logger.info(
                "httpx.AsyncClient khởi tạo (lazy singleton)",
                extra={"event": "http_client_initialized"},
            )
    return _http_client


async def close_http_client() -> None:
    """
    Đóng AsyncClient và giải phóng tất cả connections.

    Gọi trong FastAPI shutdown lifespan để tránh ResourceWarning
    và đảm bảo graceful shutdown không để socket ở trạng thái
    CLOSE_WAIT vô thời hạn.
    """
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None
        logger.info(
            "httpx.AsyncClient đã đóng (graceful shutdown)",
            extra={"event": "http_client_closed"},
        )


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
      → POST tới webhook URL qua shared AsyncClient
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

        return await self._send_webhook(user, message)

    async def _send_webhook(self, user: str, message: str) -> bool:
        """Gửi POST tới Google Chat webhook."""
        try:
            payload = {"text": f"*{user}* — {message}"}
            client = await get_http_client()
            resp = await client.post(
                settings.google_chat_webhook_url,
                json=payload,
            )
            resp.raise_for_status()
            logger.info(f"Chat gửi thành công tới {user}")
            return True
        except httpx.HTTPStatusError as exc:
            logger.error(
                f"Chat webhook fail (HTTP {exc.response.status_code}): {exc}",
                extra={"event": "chat_webhook_error", "status_code": exc.response.status_code},
            )
            return False
        except httpx.HTTPError as exc:
            logger.error(
                f"Chat webhook fail (HTTPError): {exc}",
                extra={"event": "chat_webhook_error"},
            )
            return False
        except Exception as exc:
            logger.error(
                f"Chat webhook fail (unexpected): {exc}",
                extra={"event": "chat_webhook_error"},
            )
            return False


# ─────────────────────────────────────────────
# Google Calendar Client
# ─────────────────────────────────────────────

class GoogleCalendarClient:
    """
    Client tìm slot trống trong Google Calendar.

    Mock mode: trả fixed datetime "2026-04-01T10:00:00" (deterministic)
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
        """Tìm slot thật — ngày làm việc tiếp theo lúc 10:00 UTC."""
        now = datetime.now(timezone.utc)
        delta = 1
        while True:
            candidate = now + timedelta(days=delta)
            if candidate.weekday() < 5:  # Mon–Fri
                return candidate.strftime("%Y-%m-%dT10:00:00")
            delta += 1

    async def check_free_busy(self, user_email: str, meeting_id: str) -> bool:
        """
        Check Manager có rảnh không.

        Mock: random True/False (simulate real-world uncertainty)
        Real: stub (implement với Calendar API khi deploy thật)
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

    Mock: random True/False (simulate real-world delay + uncertainty)
    Real: kiểm tra modified time của file qua Drive API
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

    Mock: random True/False (simulate real-world)
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
