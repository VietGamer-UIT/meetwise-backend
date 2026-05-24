"""
api/v1/notifications.py — Notification Endpoints

Endpoints:
  GET   /v1/thong-bao           — Danh sách thông báo
  PATCH /v1/thong-bao/{id}/doc  — Đánh dấu đã đọc
  PATCH /v1/thong-bao/doc-tat-ca — Đánh dấu tất cả đã đọc
  DELETE /v1/thong-bao/{id}     — Xóa thông báo
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from core.logging import get_logger
from middleware.auth_middleware import require_auth
from models.notification import NotificationListResponse, NotificationResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/thong-bao", tags=["🔔 Thông báo"])


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="Danh sách thông báo",
)
async def danh_sach_thong_bao(
    request: Request,
    _: None = Depends(require_auth),
    chi_chua_doc: bool = Query(default=False, description="Chỉ lấy thông báo chưa đọc"),
    gioi_han: int = Query(default=20, ge=1, le=100, description="Số thông báo tối đa"),
):
    """Lấy danh sách thông báo của user, mới nhất lên trước."""
    from integrations.supabase_client import get_supabase

    user_id = request.state.user_id
    supabase = await get_supabase()

    try:
        query = (
            supabase.table("notifications")
            .select("*", count="exact")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(gioi_han)
        )

        if chi_chua_doc:
            query = query.eq("is_read", False)

        result = await query.execute()
        items = result.data or []
        total = result.count or 0

        # Đếm chưa đọc
        unread_result = (
            await supabase.table("notifications")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .eq("is_read", False)
            .execute()
        )
        unread_count = unread_result.count or 0

        return NotificationListResponse(
            items=[NotificationResponse(**n) for n in items],
            total=total,
            unread_count=unread_count,
        )

    except Exception as exc:
        logger.error(f"Lỗi lấy thông báo: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể lấy danh sách thông báo.",
        )


@router.patch(
    "/{notification_id}/doc",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Đánh dấu thông báo đã đọc",
)
async def danh_dau_da_doc(
    notification_id: str,
    request: Request,
    _: None = Depends(require_auth),
):
    """Đánh dấu một thông báo là đã đọc."""
    from integrations.supabase_client import get_supabase
    from datetime import datetime, timezone

    user_id = request.state.user_id
    supabase = await get_supabase()

    try:
        result = (
            await supabase.table("notifications")
            .update({"is_read": True, "read_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", notification_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Thông báo không tồn tại.",
            )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Lỗi đánh dấu đã đọc: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể cập nhật thông báo.",
        )


@router.patch(
    "/doc-tat-ca",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Đánh dấu tất cả đã đọc",
)
async def doc_tat_ca(
    request: Request,
    _: None = Depends(require_auth),
):
    """Đánh dấu tất cả thông báo của user là đã đọc."""
    from integrations.supabase_client import get_supabase
    from datetime import datetime, timezone

    user_id = request.state.user_id
    supabase = await get_supabase()

    try:
        await (
            supabase.table("notifications")
            .update({"is_read": True, "read_at": datetime.now(timezone.utc).isoformat()})
            .eq("user_id", user_id)
            .eq("is_read", False)
            .execute()
        )
    except Exception as exc:
        logger.error(f"Lỗi đánh dấu tất cả đã đọc: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể cập nhật thông báo.",
        )


@router.delete(
    "/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Xóa thông báo",
)
async def xoa_thong_bao(
    notification_id: str,
    request: Request,
    _: None = Depends(require_auth),
):
    """Xóa một thông báo."""
    from integrations.supabase_client import get_supabase

    user_id = request.state.user_id
    supabase = await get_supabase()

    try:
        result = (
            await supabase.table("notifications")
            .delete()
            .eq("id", notification_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Thông báo không tồn tại.",
            )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Lỗi xóa thông báo: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể xóa thông báo.",
        )
