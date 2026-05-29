"""
tests/test_meeting_crud.py — Integration tests cho Meeting CRUD API (Phase 2)

Chiến lược test:
- Mock toàn bộ Supabase client → không kết nối DB thật
- Mock auth_middleware → tự động inject user giả vào mọi request
- Test đầy đủ: tạo, lấy danh sách, chi tiết, cập nhật, xóa, trigger AI

Tác giả: Đoàn Hoàng Việt (Việt Gamer)
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta, timezone
import uuid

from main import app


# ─────────────────────────────────────────────────────────────
# Dữ liệu giả (mock data)
# ─────────────────────────────────────────────────────────────

FAKE_USER_ID = str(uuid.uuid4())
FAKE_USER = {
    "id": FAKE_USER_ID,
    "email": "test@meetwise.app",
    "full_name": "Người Dùng Test",
}

FAKE_MEETING_ID = str(uuid.uuid4())
FAKE_MEETING = {
    "id": FAKE_MEETING_ID,
    "owner_id": FAKE_USER_ID,
    "title": "Họp Q1 2026 — Kickoff",
    "description": "Cuộc họp khởi động quý 1",
    "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
    "duration_minutes": 60,
    "location": "Phòng họp 3A",
    "meeting_url": "https://meet.google.com/abc-xyz",
    "rule": "Slide_Done AND Manager_Free",
    "status": "pending",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "last_evaluated_at": None,
    "team_id": str(uuid.uuid4()),
}

FAKE_MEETING_LIST = {
    "items": [FAKE_MEETING],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "has_next": False,
}

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_supabase_mock(meeting_data=None, list_data=None):
    """Tạo mock Supabase client hoàn chỉnh với chain methods."""
    mock = MagicMock()

    # Mock chain: supabase.table(...).select(...).eq(...).execute()
    execute_result = MagicMock()
    execute_result.data = [meeting_data] if meeting_data else []

    chain = MagicMock()
    chain.execute = MagicMock(return_value=execute_result)
    chain.eq = MagicMock(return_value=chain)
    chain.order = MagicMock(return_value=chain)
    chain.limit = MagicMock(return_value=chain)
    chain.offset = MagicMock(return_value=chain)
    chain.select = MagicMock(return_value=chain)
    chain.insert = MagicMock(return_value=chain)
    chain.update = MagicMock(return_value=chain)
    chain.delete = MagicMock(return_value=chain)
    chain.single = MagicMock(return_value=chain)

    mock.table = MagicMock(return_value=chain)
    return mock, chain


@pytest_asyncio.fixture
async def client():
    """Async HTTP client với mock Supabase và auth middleware."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        # Header giả lập JWT token (sẽ bị mock ở middleware)
        headers={"Authorization": "Bearer fake-jwt-token-for-testing"},
    ) as ac:
        yield ac


# ─────────────────────────────────────────────────────────────
# Helper: patch auth + supabase đồng thời
# ─────────────────────────────────────────────────────────────

from fastapi import Request

class MockAuthContext:
    def __enter__(self):
        from middleware.auth_middleware import require_auth
        async def fake_auth(request: Request):
            request.state.user_id = FAKE_USER_ID
            request.state.user_email = FAKE_USER["email"]
            request.state.user_role = "authenticated"
        app.dependency_overrides[require_auth] = fake_auth
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        from middleware.auth_middleware import require_auth
        app.dependency_overrides.pop(require_auth, None)

def mock_auth():
    """Context manager mock auth_middleware để inject user giả."""
    return MockAuthContext()


def mock_supabase(meeting_data=None):
    """Context manager mock Supabase client."""
    mock, chain = _make_supabase_mock(meeting_data=meeting_data)
    return patch(
        "integrations.supabase_client.get_supabase",
        return_value=mock,
    ), mock, chain


# ─────────────────────────────────────────────────────────────
# Test: Tạo cuộc họp mới (POST /v1/cuoc-hop)
# ─────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_tao_cuoc_hop_thanh_cong(client: AsyncClient):
    """
    POST /v1/cuoc-hop — Tạo cuộc họp mới với đầy đủ thông tin.
    Expected: 201 Created + dữ liệu cuộc họp mới.
    """
    payload = {
        "title": "Họp Q1 2026 — Kickoff",
        "description": "Cuộc họp khởi động quý 1",
        "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        "duration_minutes": 60,
        "location": "Phòng họp 3A",
        "rule": "Slide_Done AND Manager_Free",
    }

    supabase_mock = MagicMock()
    chain = MagicMock()
    chain.execute.return_value.data = [FAKE_MEETING]
    supabase_mock.table.return_value = chain
    chain.insert.return_value.select.return_value.single.return_value = chain

    with mock_auth(), \
         patch("integrations.supabase_client.get_supabase", return_value=supabase_mock), \
         patch("services.meeting_crud_service.MeetingCRUDService.create", new_callable=AsyncMock, return_value=FAKE_MEETING):

        response = await client.post("/v1/cuoc-hop", json=payload)

    # Kiểm tra kết quả
    assert response.status_code in (200, 201), f"Expected 2xx, got {response.status_code}: {response.text}"
    data = response.json()
    assert "id" in data
    assert data["title"] == "Họp Q1 2026 — Kickoff"
    assert data["rule"] == "Slide_Done AND Manager_Free"
    assert data["status"] == "pending"


@pytest.mark.anyio
async def test_tao_cuoc_hop_thieu_title(client: AsyncClient):
    """
    POST /v1/cuoc-hop — Thiếu title → 400 hoặc 422.
    """
    payload = {
        "description": "Không có tiêu đề",
        "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        "rule": "Slide_Done",
    }

    with mock_auth():
        response = await client.post("/v1/cuoc-hop", json=payload)

    assert response.status_code in (400, 422), f"Expected 4xx validation error, got {response.status_code}"


@pytest.mark.anyio
async def test_tao_cuoc_hop_thieu_rule(client: AsyncClient):
    """
    POST /v1/cuoc-hop — Thiếu rule → 400 hoặc 422.
    AI không thể đánh giá nếu không có điều kiện.
    """
    payload = {
        "title": "Họp quan trọng",
        "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        # Thiếu rule
    }

    with mock_auth():
        response = await client.post("/v1/cuoc-hop", json=payload)

    assert response.status_code in (400, 422), f"Expected 4xx, got {response.status_code}"


# ─────────────────────────────────────────────────────────────
# Test: Lấy danh sách cuộc họp (GET /v1/cuoc-hop)
# ─────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_lay_danh_sach_cuoc_hop(client: AsyncClient):
    """
    GET /v1/cuoc-hop — Lấy danh sách cuộc họp của user.
    Expected: 200 + danh sách cuộc họp + metadata phân trang.
    """
    with mock_auth(), \
         patch("services.meeting_crud_service.MeetingCRUDService.list_meetings", new_callable=AsyncMock, return_value=FAKE_MEETING_LIST):

        response = await client.get("/v1/cuoc-hop")

    assert response.status_code == 200, f"Response: {response.text}"
    data = response.json()

    # Phải có cấu trúc list response
    assert "items" in data, "Response phải có 'items'"
    assert "total" in data, "Response phải có 'total'"
    assert isinstance(data["items"], list), "items phải là list"
    assert data["total"] >= 0, "total phải >= 0"


@pytest.mark.anyio
async def test_lay_danh_sach_co_filter_trang_thai(client: AsyncClient):
    """
    GET /v1/cuoc-hop?trang_thai=pending — Filter theo trạng thái.
    Expected: 200 + chỉ trả về cuộc họp pending.
    """
    filtered_list = {
        **FAKE_MEETING_LIST,
        "items": [m for m in FAKE_MEETING_LIST["items"] if m["status"] == "pending"],
    }

    with mock_auth(), \
         patch("services.meeting_crud_service.MeetingCRUDService.list_meetings", new_callable=AsyncMock, return_value=filtered_list):

        response = await client.get("/v1/cuoc-hop?trang_thai=pending")

    assert response.status_code == 200
    data = response.json()
    for item in data.get("items", []):
        assert item["status"] == "pending", f"Item không đúng status: {item['status']}"


@pytest.mark.anyio
async def test_lay_danh_sach_phan_trang(client: AsyncClient):
    """
    GET /v1/cuoc-hop?trang=1&kich_thuoc=5 — Phân trang.
    Expected: 200, kich_thuoc <= 5.
    """
    with mock_auth(), \
         patch("services.meeting_crud_service.MeetingCRUDService.list_meetings", new_callable=AsyncMock, return_value=FAKE_MEETING_LIST):

        response = await client.get("/v1/cuoc-hop?trang=1&kich_thuoc=5")

    assert response.status_code == 200
    data = response.json()
    assert len(data.get("items", [])) <= 5, "Số items không được vượt quá kich_thuoc"


# ─────────────────────────────────────────────────────────────
# Test: Chi tiết cuộc họp (GET /v1/cuoc-hop/{id})
# ─────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_lay_chi_tiet_cuoc_hop(client: AsyncClient):
    """
    GET /v1/cuoc-hop/{id} — Lấy chi tiết một cuộc họp.
    Expected: 200 + đầy đủ thông tin cuộc họp.
    """
    with mock_auth(), \
         patch("services.meeting_crud_service.MeetingCRUDService.get_by_id", new_callable=AsyncMock, return_value=FAKE_MEETING):

        response = await client.get(f"/v1/cuoc-hop/{FAKE_MEETING_ID}")

    assert response.status_code == 200, f"Response: {response.text}"
    data = response.json()
    assert data["id"] == FAKE_MEETING_ID
    assert "title" in data
    assert "rule" in data
    assert "status" in data


@pytest.mark.anyio
async def test_lay_chi_tiet_khong_ton_tai(client: AsyncClient):
    """
    GET /v1/cuoc-hop/{id} — ID không tồn tại → 404.
    """
    from fastapi import HTTPException

    with mock_auth(), \
         patch("services.meeting_crud_service.MeetingCRUDService.get_by_id", new_callable=AsyncMock, side_effect=HTTPException(status_code=404, detail="Không tìm thấy cuộc họp")):

        response = await client.get(f"/v1/cuoc-hop/{uuid.uuid4()}")

    assert response.status_code == 404, f"Expected 404, got {response.status_code}"


# ─────────────────────────────────────────────────────────────
# Test: Trigger AI Evaluation (POST /v1/cuoc-hop/{id}/danh-gia)
# ─────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_kich_hoat_danh_gia_ai(client: AsyncClient):
    """
    POST /v1/cuoc-hop/{id}/danh-gia — Kích hoạt AI đánh giá.
    Expected: 200 + kết quả READY hoặc RESCHEDULED.
    """
    fake_result = {
        **FAKE_MEETING,
        "status": "rescheduled",
        "last_evaluated_at": datetime.now(timezone.utc).isoformat(),
        "ai_result": {
            "status": "RESCHEDULED",
            "reason": "Manager_Free chưa thỏa mãn",
            "unsatisfied_conditions": ["Manager_Free"],
        },
    }

    with mock_auth(), \
         patch("services.meeting_crud_service.MeetingCRUDService.get_by_id", new_callable=AsyncMock, return_value=FAKE_MEETING), \
         patch("services.meeting_crud_service.MeetingCRUDService.trigger_ai_evaluation", new_callable=AsyncMock, return_value=fake_result):

        response = await client.post(f"/v1/cuoc-hop/{FAKE_MEETING_ID}/danh-gia")

    assert response.status_code == 200, f"Response: {response.text}"
    data = response.json()
    assert data["status"] in ("ready", "rescheduled", "evaluating", "pending"), \
        f"Status không hợp lệ: {data['status']}"


@pytest.mark.anyio
async def test_danh_gia_khong_co_auth(client: AsyncClient):
    """
    POST /v1/cuoc-hop/{id}/danh-gia — Không có JWT token → 401.
    Chú ý: test này dùng client không có Authorization header.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        # Không có Authorization header
    ) as no_auth_client:
        response = await no_auth_client.post(f"/v1/cuoc-hop/{FAKE_MEETING_ID}/danh-gia")

    # Phải từ chối request không có auth
    assert response.status_code in (401, 403, 422), \
        f"Expected 401/403, got {response.status_code}"


# ─────────────────────────────────────────────────────────────
# Test: Xóa cuộc họp (DELETE /v1/cuoc-hop/{id})
# ─────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_xoa_cuoc_hop_thanh_cong(client: AsyncClient):
    """
    DELETE /v1/cuoc-hop/{id} — Xóa cuộc họp.
    Expected: 200 hoặc 204.
    """
    with mock_auth(), \
         patch("services.meeting_crud_service.MeetingCRUDService.get_by_id", new_callable=AsyncMock, return_value=FAKE_MEETING), \
         patch("services.meeting_crud_service.MeetingCRUDService.delete", new_callable=AsyncMock, return_value={"message": "Đã xóa thành công"}):

        response = await client.delete(f"/v1/cuoc-hop/{FAKE_MEETING_ID}")

    assert response.status_code in (200, 204), f"Expected 2xx, got {response.status_code}"


@pytest.mark.anyio
async def test_xoa_cuoc_hop_khong_ton_tai(client: AsyncClient):
    """
    DELETE /v1/cuoc-hop/{id} — Xóa ID không tồn tại → 404.
    """
    from fastapi import HTTPException

    with mock_auth(), \
         patch("services.meeting_crud_service.MeetingCRUDService.get_by_id", new_callable=AsyncMock, side_effect=HTTPException(status_code=404, detail="Không tìm thấy")), \
         patch("services.meeting_crud_service.MeetingCRUDService.delete", new_callable=AsyncMock, side_effect=HTTPException(status_code=404, detail="Không tìm thấy")):

        response = await client.delete(f"/v1/cuoc-hop/{uuid.uuid4()}")

    assert response.status_code == 404, f"Expected 404, got {response.status_code}"
