"""
api/v1/dashboard.py — Dashboard Statistics Endpoint

Endpoints:
  GET /v1/bang-dieu-khien/thong-ke    — Số liệu tổng quan cho dashboard
  GET /v1/bang-dieu-khien/cuoc-hop-gan-day — 5 cuộc họp sắp diễn ra
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from typing import List, Optional

from core.logging import get_logger
from middleware.auth_middleware import require_auth

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/bang-dieu-khien", tags=["📊 Dashboard"])


class ThongKeDashboard(BaseModel):
    tong_cuoc_hop: int
    san_sang: int
    can_doi_lich: int
    cho_danh_gia: int
    da_danh_gia_hom_nay: int
    ti_le_san_sang: float  # Phần trăm cuộc họp READY


class CuocHopGanDay(BaseModel):
    id: str
    title: str
    scheduled_at: str
    status: str
    rule: str


@router.get(
    "/thong-ke",
    response_model=ThongKeDashboard,
    summary="Số liệu tổng quan dashboard",
)
async def lay_thong_ke(
    request: Request,
    _: None = Depends(require_auth),
):
    """
    Trả về thống kê tổng quan:
    - Tổng số cuộc họp
    - Số cuộc họp READY / RESCHEDULED / PENDING
    - Số cuộc họp đã đánh giá hôm nay
    - Tỉ lệ sẵn sàng (%)
    """
    from integrations.supabase_client import get_supabase

    user_id = request.state.user_id
    supabase = await get_supabase()

    try:
        # Lấy tất cả meetings của user (chỉ cần status)
        result = (
            await supabase.table("meetings")
            .select("status, last_evaluated_at")
            .eq("owner_id", user_id)
            .execute()
        )

        rows = result.data or []
        tong = len(rows)
        san_sang = sum(1 for r in rows if r["status"] == "ready")
        can_doi_lich = sum(1 for r in rows if r["status"] == "rescheduled")
        cho_danh_gia = sum(1 for r in rows if r["status"] in ("pending", "evaluating"))

        # Đánh giá hôm nay
        from datetime import datetime, timezone, timedelta
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        da_danh_gia_hom_nay = sum(
            1 for r in rows
            if r.get("last_evaluated_at") and r["last_evaluated_at"] >= today_start.isoformat()
        )

        # Tỉ lệ sẵn sàng
        evaluated = san_sang + can_doi_lich
        ti_le = round((san_sang / evaluated * 100), 1) if evaluated > 0 else 0.0

        return ThongKeDashboard(
            tong_cuoc_hop=tong,
            san_sang=san_sang,
            can_doi_lich=can_doi_lich,
            cho_danh_gia=cho_danh_gia,
            da_danh_gia_hom_nay=da_danh_gia_hom_nay,
            ti_le_san_sang=ti_le,
        )

    except Exception as exc:
        logger.error(f"Lỗi lấy thống kê dashboard: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể lấy dữ liệu dashboard.",
        )


@router.get(
    "/cuoc-hop-gan-day",
    response_model=List[CuocHopGanDay],
    summary="Cuộc họp sắp diễn ra",
)
async def cuoc_hop_gan_day(
    request: Request,
    _: None = Depends(require_auth),
):
    """Lấy 5 cuộc họp sắp diễn ra gần nhất (từ hiện tại trở đi)."""
    from integrations.supabase_client import get_supabase
    from datetime import datetime, timezone

    user_id = request.state.user_id
    supabase = await get_supabase()

    try:
        now = datetime.now(timezone.utc).isoformat()

        result = (
            await supabase.table("meetings")
            .select("id, title, scheduled_at, status, rule")
            .eq("owner_id", user_id)
            .gte("scheduled_at", now)
            .neq("status", "cancelled")
            .order("scheduled_at", desc=False)
            .limit(5)
            .execute()
        )

        return [
            CuocHopGanDay(
                id=r["id"],
                title=r["title"],
                scheduled_at=r["scheduled_at"],
                status=r["status"],
                rule=r["rule"],
            )
            for r in (result.data or [])
        ]

    except Exception as exc:
        logger.error(f"Lỗi lấy cuộc họp gần đây: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể lấy danh sách cuộc họp.",
        )
