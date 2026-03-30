"""
agent/tools.py — Async Tool Layer (v3 Zero-Setup)

Khi USE_GOOGLE_SERVICES=false (default):
  - Dùng mock Google APIs (realistic random True/False)
  - Không cần bất kỳ credential nào

Khi USE_GOOGLE_SERVICES=true:
  - Ưu tiên gọi Google Drive/Sheets/Calendar API thật
  - Fallback về MockFirestore nếu Real API fail

Retry + Timeout decorator áp dụng cho mọi tool.
"""

import asyncio
import random
from functools import wraps
from typing import Any, Callable, Dict, List

from core.config import settings
from core.logging import get_logger
from storage.firestore_client import firestore_client

logger = get_logger(__name__)


# ─────────────────────────────────────────────
# Retry + Timeout Decorator
# ─────────────────────────────────────────────

def async_tool(
    max_retries: int = 3,
    timeout: float = None,
    fallback_value: Any = False,
):
    """
    Decorator cho async tool functions:
    - Timeout mỗi lần gọi
    - Retry với exponential backoff
    - Fallback value nếu tất cả retries fail
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            _timeout = timeout or settings.step_timeout_seconds
            tool_name = func.__name__

            for attempt in range(1, max_retries + 1):
                try:
                    result = await asyncio.wait_for(
                        func(*args, **kwargs),
                        timeout=_timeout,
                    )
                    if attempt > 1:
                        logger.info(
                            f"Tool '{tool_name}' thành công sau {attempt} lần",
                            extra={"event": "tool_retry_success", "tool": tool_name, "attempt": attempt},
                        )
                    return result

                except asyncio.TimeoutError:
                    logger.warning(
                        f"Tool '{tool_name}' timeout (attempt {attempt}/{max_retries})",
                        extra={"event": "tool_timeout", "tool": tool_name, "attempt": attempt},
                    )
                except Exception as exc:
                    logger.warning(
                        f"Tool '{tool_name}' lỗi (attempt {attempt}/{max_retries}): {exc}",
                        extra={"event": "tool_error", "tool": tool_name, "attempt": attempt, "error": str(exc)},
                    )

                if attempt < max_retries:
                    await asyncio.sleep(0.1 * (2 ** (attempt - 1)))

            logger.error(
                f"Tool '{tool_name}' thất bại → fallback={fallback_value}",
                extra={"event": "tool_fallback", "tool": tool_name},
            )
            return fallback_value

        return wrapper
    return decorator


# ─────────────────────────────────────────────
# Tool Functions
# ─────────────────────────────────────────────

@async_tool(max_retries=2, fallback_value=False)
async def fetch_slide_status(meeting_id: str) -> bool:
    """
    Lấy trạng thái Slide.

    USE_GOOGLE_SERVICES=false: random True/False (mock realistic)
    USE_GOOGLE_SERVICES=true:  Google Drive API thật
    """
    if not settings.use_google_services:
        # Mock: simulate realistic random behavior
        from integrations.google_workspace import google_drive
        result = await google_drive.check_slide_updated(meeting_id)
        logger.info(
            f"[MOCK] Slide status '{meeting_id}': {result}",
            extra={"event": "tool_result", "tool": "fetch_slide_status", "result": result},
        )
        return result

    # Real: đọc từ Firestore (đã được set bởi Google Drive webhook)
    return await firestore_client.get_fact(meeting_id, "Slide_Done", default=False)


@async_tool(max_retries=2, fallback_value=False)
async def fetch_sheet_status(meeting_id: str) -> bool:
    """
    Lấy trạng thái Sheet.

    Mock: random | Real: Google Sheets API
    """
    if not settings.use_google_services:
        from integrations.google_workspace import google_sheets
        result = await google_sheets.check_sheet_finalized(meeting_id)
        logger.info(
            f"[MOCK] Sheet status '{meeting_id}': {result}",
            extra={"event": "tool_result", "tool": "fetch_sheet_status", "result": result},
        )
        return result

    return await firestore_client.get_fact(meeting_id, "Sheet_Done", default=False)


@async_tool(max_retries=2, fallback_value=False)
async def fetch_manager_availability(meeting_id: str) -> bool:
    """
    Lấy trạng thái lịch Manager.

    Mock: random | Real: Google Calendar API
    """
    if not settings.use_google_services:
        from integrations.google_workspace import google_calendar
        result = await google_calendar.check_free_busy("manager@company.com", meeting_id)
        logger.info(
            f"[MOCK] Manager availability '{meeting_id}': {result}",
            extra={"event": "tool_result", "tool": "fetch_manager_availability", "result": result},
        )
        return result

    return await firestore_client.get_fact(meeting_id, "Manager_Free", default=False)


@async_tool(max_retries=2, fallback_value=True)
async def fetch_attendees_confirmed(meeting_id: str) -> bool:
    """Kiểm tra attendees đã xác nhận. Mock: True (optimistic)."""
    if not settings.use_google_services:
        return True  # Default optimistic trong mock mode

    return await firestore_client.get_fact(meeting_id, "Attendees_Confirmed", default=True)


# ─────────────────────────────────────────────
# Tool Registry + Parallel Fetch
# ─────────────────────────────────────────────

TOOL_REGISTRY: Dict[str, Callable] = {
    "Slide_Done":          fetch_slide_status,
    "Sheet_Done":          fetch_sheet_status,
    "Manager_Free":        fetch_manager_availability,
    "Attendees_Confirmed": fetch_attendees_confirmed,
}


async def fetch_facts_parallel(
    meeting_id: str,
    required_keys: List[str],
) -> Dict[str, bool]:
    """
    Gọi song song các tools cần thiết.
    Chỉ gọi tools cho keys có trong required_keys.
    """
    tasks = {}
    for key in required_keys:
        tool = TOOL_REGISTRY.get(key)
        if tool:
            tasks[key] = asyncio.create_task(tool(meeting_id))
        else:
            logger.warning(f"Không có tool cho fact '{key}' → dùng False")

    results: Dict[str, bool] = {}
    if tasks:
        completed = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for key, result in zip(tasks.keys(), completed):
            if isinstance(result, Exception):
                logger.error(f"Tool '{key}' raise exception: {result}")
                results[key] = False
            else:
                results[key] = bool(result)

    return results
