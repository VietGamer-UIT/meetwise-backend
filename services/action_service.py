"""
services/action_service.py — Action Execution Layer (v3 Zero-Setup)

Mock mode (USE_GOOGLE_SERVICES=false, default):
  - send_chat() → print "[MOCK CHAT] Gửi tới Manager: ..."
  - suggest_time() → trả fixed "2026-04-01T10:00:00"
  - execute_actions() → asyncio.gather (song song)

Real mode (USE_GOOGLE_SERVICES=true):
  - send_chat() → Google Chat webhook thật
  - suggest_time() → Google Calendar FreeBusy API

Actions KHÔNG BAO GIỜ fail API — error → log + continue.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from integrations.google_workspace import google_chat, google_calendar
from schemas.response import ActionResult, ActionStatus, ActionType
from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

# Fixed time cho mock → deterministic response cho FE dev
_MOCK_PROPOSED_TIME = "2026-04-01T10:00:00"

# ─────────────────────────────────────────────
# Condition → Action Target Mapping
# ─────────────────────────────────────────────

_CONDITION_TO_TARGET: Dict[str, tuple[str, str]] = {
    "Manager_Free":        ("Manager",      "quản lý lịch họp"),
    "Sheet_Done":          ("Analyst",      "người phụ trách số liệu (Sheets)"),
    "Slide_Done":          ("Owner",        "người phụ trách tài liệu (Slides)"),
    "Attendees_Confirmed": ("Participants", "các thành viên tham dự"),
}

# Conditions kích hoạt RESCHEDULE
_RESCHEDULE_TRIGGERS = {"Manager_Free", "Attendees_Confirmed"}


# ─────────────────────────────────────────────
# Core Tools
# ─────────────────────────────────────────────

async def send_chat(user: str, message: str) -> bool:
    """
    Gửi chat notification.

    Mock: print log "[MOCK CHAT] Gửi tới {user}: {message}"
    Real: gọi Google Chat webhook
    """
    try:
        result = await google_chat.send_message(user=user, message=message)
        return result
    except Exception as exc:
        logger.error(
            f"send_chat thất bại tới '{user}': {exc}",
            extra={"event": "send_chat_error", "target": user},
        )
        return False


async def suggest_time(meeting_id: str) -> str:
    """
    Đề xuất thời gian họp mới.

    Mock: trả fixed "2026-04-01T10:00:00"
    Real: gọi Google Calendar API
    Returns: ISO 8601 datetime string
    """
    try:
        proposed = await google_calendar.find_next_slot(meeting_id=meeting_id)
        return proposed
    except Exception as exc:
        logger.error(
            f"suggest_time thất bại: {exc}",
            extra={"event": "suggest_time_error", "meeting_id": meeting_id},
        )
        # Fallback: ngày mai lúc 10:00
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        return tomorrow.strftime("%Y-%m-%dT10:00:00")


# ─────────────────────────────────────────────
# Main Execute (asyncio.gather)
# ─────────────────────────────────────────────

async def execute_actions(
    unsatisfied_conditions: List[str],
    meeting_id: str,
    reason: str,
) -> List[ActionResult]:
    """
    Thực thi tất cả actions song song bằng asyncio.gather.

    Flow:
    1. Mỗi unsatisfied condition → NOTIFY action
    2. Nếu có Manager_Free hoặc Attendees_Confirmed → RESCHEDULE action
    3. Tất cả chạy đồng thời, không block nhau
    4. Fail → FAILED status, không raise

    Returns:
        List[ActionResult] — tất cả actions đã thực thi
    """
    if not unsatisfied_conditions:
        return []

    logger.info(
        f"execute_actions bắt đầu: {len(unsatisfied_conditions)} conditions",
        extra={
            "event": "actions_start",
            "meeting_id": meeting_id,
            "conditions": unsatisfied_conditions,
        },
    )

    # Build coroutines
    tasks: List[asyncio.Coroutine] = []

    for condition in unsatisfied_conditions:
        target_info = _CONDITION_TO_TARGET.get(condition)
        target_name = target_info[0] if target_info else condition
        target_role  = target_info[1] if target_info else "liên quan"

        message = (
            f"Cuộc họp không thể diễn ra: {reason}\n"
            f"Điều kiện chưa thỏa mãn: *{condition}* ({target_role}).\n"
            f"Vui lòng hoàn thành để cuộc họp có thể tiếp tục.\n"
            f"Meeting ID: {meeting_id}"
        )

        tasks.append(_execute_notify(target_name, message, condition))

    # RESCHEDULE nếu cần
    needs_reschedule = any(c in _RESCHEDULE_TRIGGERS for c in unsatisfied_conditions)
    if needs_reschedule:
        tasks.append(_execute_reschedule(meeting_id))

    # Chạy TẤT CẢ song song
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect kết quả
    action_results: List[ActionResult] = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Action exception: {result}", extra={"event": "action_exception"})
            action_results.append(ActionResult(
                type=ActionType.NOTIFY,
                target="unknown",
                status=ActionStatus.FAILED,
                error="Action gặp lỗi không mong đợi",
            ))
        elif isinstance(result, ActionResult):
            action_results.append(result)

    logger.info(
        f"execute_actions hoàn thành: {len(action_results)} actions",
        extra={
            "event": "actions_complete",
            "meeting_id": meeting_id,
            "total": len(action_results),
            "success": sum(1 for a in action_results if a.status == ActionStatus.SENT),
        },
    )

    return action_results


# ─────────────────────────────────────────────
# Internal Helpers
# ─────────────────────────────────────────────

async def _execute_notify(target: str, message: str, condition: str) -> ActionResult:
    """Thực thi NOTIFY action. Trả ActionResult dù thành công hay thất bại."""
    try:
        success = await asyncio.wait_for(
            send_chat(user=target, message=message),
            timeout=settings.action_timeout_seconds,
        )
        status = ActionStatus.SENT if success else ActionStatus.FAILED
        error = None if success else "Gửi message thất bại"

        logger.info(
            f"NOTIFY → {target}: {status.value}",
            extra={"event": "notify_result", "target": target, "condition": condition, "status": status.value},
        )

        return ActionResult(
            type=ActionType.NOTIFY,
            target=target,
            status=status,
            message=message[:200] + "..." if len(message) > 200 else message,
            error=error,
        )

    except asyncio.TimeoutError:
        logger.warning(f"NOTIFY timeout → {target}", extra={"event": "notify_timeout"})
        return ActionResult(
            type=ActionType.NOTIFY,
            target=target,
            status=ActionStatus.FAILED,
            error="Timeout khi gửi notification",
        )
    except Exception as exc:
        logger.error(f"NOTIFY error → {target}: {exc}", extra={"event": "notify_error"})
        return ActionResult(
            type=ActionType.NOTIFY,
            target=target,
            status=ActionStatus.FAILED,
            error="Lỗi hệ thống khi gửi notification",
        )


async def _execute_reschedule(meeting_id: str) -> ActionResult:
    """Thực thi RESCHEDULE action."""
    try:
        proposed_time = await asyncio.wait_for(
            suggest_time(meeting_id),
            timeout=settings.action_timeout_seconds,
        )

        logger.info(
            f"RESCHEDULE → proposed={proposed_time}",
            extra={"event": "reschedule_result", "meeting_id": meeting_id, "proposed_time": proposed_time},
        )

        return ActionResult(
            type=ActionType.RESCHEDULE,
            target=None,
            status=ActionStatus.SENT,
            proposed_time=proposed_time,
        )

    except asyncio.TimeoutError:
        return ActionResult(
            type=ActionType.RESCHEDULE,
            target=None,
            status=ActionStatus.FAILED,
            error="Timeout khi tìm thời gian trống",
        )
    except Exception as exc:
        logger.error(f"RESCHEDULE error: {exc}", extra={"event": "reschedule_error"})
        return ActionResult(
            type=ActionType.RESCHEDULE,
            target=None,
            status=ActionStatus.FAILED,
            error="Lỗi hệ thống khi đề xuất lịch",
        )
