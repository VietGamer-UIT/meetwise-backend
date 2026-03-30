"""
tests/test_actions.py — Unit tests cho Action Service Layer
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from schemas.response import ActionStatus, ActionType


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


# ─────────────────────────────────────────────
# send_chat Tests
# ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_send_chat_mock_mode():
    """send_chat trong MOCK mode luôn trả True."""
    from services.action_service import send_chat

    # MOCK mode: google_chat._mock_mode = True (mặc định nếu không set webhook)
    result = await send_chat("Manager", "Test message")
    assert isinstance(result, bool)
    # Mock mode luôn thành công
    assert result is True


@pytest.mark.anyio
async def test_send_chat_failure_returns_false():
    """send_chat fail → trả False, không raise."""
    from services.action_service import send_chat

    with patch(
        "integrations.google_workspace.google_chat.send_message",
        side_effect=Exception("Connection refused"),
    ):
        result = await send_chat("Manager", "Test message")
        assert result is False


# ─────────────────────────────────────────────
# suggest_time Tests
# ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_suggest_time_returns_iso_string():
    """suggest_time trả về ISO 8601 string."""
    from services.action_service import suggest_time

    result = await suggest_time("test-meeting-001")
    assert isinstance(result, str)
    # Phải có định dạng YYYY-MM-DDTHH:MM:SS
    assert "T" in result
    assert len(result) >= 16  # Ít nhất YYYY-MM-DDTHH:MM


@pytest.mark.anyio
async def test_suggest_time_failure_fallback():
    """suggest_time fail → fallback ngày hôm sau, không raise."""
    from services.action_service import suggest_time

    with patch(
        "integrations.google_workspace.google_calendar.find_next_slot",
        side_effect=Exception("Calendar API down"),
    ):
        result = await suggest_time("test-meeting-001")
        # Phải có fallback value
        assert isinstance(result, str)
        assert "T" in result


# ─────────────────────────────────────────────
# execute_actions Tests
# ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_execute_actions_empty_conditions():
    """Không có unsatisfied conditions → trả về list rỗng."""
    from services.action_service import execute_actions

    result = await execute_actions(
        unsatisfied_conditions=[],
        meeting_id="test-001",
        reason="",
    )
    assert result == []


@pytest.mark.anyio
async def test_execute_actions_manager_free_fails():
    """
    Manager_Free UNSAT → NOTIFY Manager + RESCHEDULE actions.
    """
    from services.action_service import execute_actions

    result = await execute_actions(
        unsatisfied_conditions=["Manager_Free"],
        meeting_id="test-mandatory-001",
        reason="Manager chưa rảnh lịch.",
    )

    assert len(result) >= 2, "Phải có ít nhất NOTIFY + RESCHEDULE"

    types = {a.type for a in result}
    assert ActionType.NOTIFY in types, "Phải có NOTIFY action"
    assert ActionType.RESCHEDULE in types, "Phải có RESCHEDULE action (Manager_Free trigger)"

    notify = next(a for a in result if a.type == ActionType.NOTIFY)
    assert notify.target == "Manager"
    assert notify.status in (ActionStatus.SENT, ActionStatus.FAILED)


@pytest.mark.anyio
async def test_execute_actions_slide_done_fails():
    """Slide_Done UNSAT → NOTIFY Owner. Không trigger RESCHEDULE."""
    from services.action_service import execute_actions

    result = await execute_actions(
        unsatisfied_conditions=["Slide_Done"],
        meeting_id="test-slide-001",
        reason="Slide chưa được cập nhật.",
    )

    assert len(result) >= 1

    notify_actions = [a for a in result if a.type == ActionType.NOTIFY]
    assert len(notify_actions) == 1
    assert notify_actions[0].target == "Owner"

    # Slide_Done không trigger RESCHEDULE
    reschedule_actions = [a for a in result if a.type == ActionType.RESCHEDULE]
    assert len(reschedule_actions) == 0, "Slide_Done không trigger RESCHEDULE"


@pytest.mark.anyio
async def test_execute_actions_multiple_unsat():
    """Nhiều conditions UNSAT → nhiều NOTIFY + 1 RESCHEDULE (nếu có trigger)."""
    from services.action_service import execute_actions

    result = await execute_actions(
        unsatisfied_conditions=["Manager_Free", "Slide_Done"],
        meeting_id="test-multi-001",
        reason="Cả Manager và Slide đều chưa sẵn sàng.",
    )

    types = [a.type for a in result]
    notify_count = types.count(ActionType.NOTIFY)
    reschedule_count = types.count(ActionType.RESCHEDULE)

    assert notify_count == 2, "Phải có 2 NOTIFY (Manager + Owner)"
    assert reschedule_count == 1, "Chỉ 1 RESCHEDULE dù có nhiều triggers"


@pytest.mark.anyio
async def test_execute_actions_chat_fail_does_not_raise():
    """Chat fail → action status=failed, execute_actions không raise."""
    from services.action_service import execute_actions

    with patch(
        "services.action_service.send_chat",
        side_effect=Exception("Network error"),
    ):
        result = await execute_actions(
            unsatisfied_conditions=["Manager_Free"],
            meeting_id="test-fail-001",
            reason="Test",
        )

    # Vẫn phải có kết quả, không raise
    assert isinstance(result, list)
    # Notify action phải có status=failed
    notify_actions = [a for a in result if a.type == ActionType.NOTIFY]
    for na in notify_actions:
        assert na.status == ActionStatus.FAILED


@pytest.mark.anyio
async def test_action_result_structure():
    """Kiểm tra cấu trúc ActionResult sau execute_actions."""
    from services.action_service import execute_actions

    result = await execute_actions(
        unsatisfied_conditions=["Manager_Free"],
        meeting_id="test-struct-001",
        reason="Test reason",
    )

    for action in result:
        # type bắt buộc
        assert action.type in (ActionType.NOTIFY, ActionType.RESCHEDULE)
        # status bắt buộc
        assert action.status in (ActionStatus.SENT, ActionStatus.FAILED, ActionStatus.SKIPPED)
        # RESCHEDULE phải có proposed_time nếu sent
        if action.type == ActionType.RESCHEDULE and action.status == ActionStatus.SENT:
            assert action.proposed_time is not None
        # Action result phải serializable
        action_dict = action.model_dump()
        assert "type" in action_dict
        assert "status" in action_dict
