"""
api/v1/meeting_crud.py — Meeting CRUD + AI Evaluation Endpoints

Endpoints:
  POST   /v1/cuoc-hop                          — Tạo cuộc họp mới
  GET    /v1/cuoc-hop                          — Danh sách cuộc họp (phân trang)
  GET    /v1/cuoc-hop/{id}                     — Chi tiết cuộc họp
  PATCH  /v1/cuoc-hop/{id}                     — Cập nhật cuộc họp
  DELETE /v1/cuoc-hop/{id}                     — Xóa cuộc họp
  POST   /v1/cuoc-hop/{id}/danh-gia            — Trigger AI evaluation
  GET    /v1/cuoc-hop/{id}/lich-su-danh-gia    — Lịch sử AI đánh giá
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from core.logging import get_logger
from middleware.auth_middleware import require_auth
from models.meeting import MeetingCreate, MeetingListResponse, MeetingResponse, MeetingUpdate
from services.meeting_crud_service import meeting_crud_service

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/cuoc-hop", tags=["📅 Cuộc họp"])


@router.post(
    "",
    response_model=MeetingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo cuộc họp mới",
)
async def tao_cuoc_hop(
    body: MeetingCreate,
    request: Request,
    _: None = Depends(require_auth),
):
    """Tạo một cuộc họp mới. AI sẽ đánh giá khi bạn gọi endpoint /danh-gia."""
    try:
        return await meeting_crud_service.create(
            user_id=request.state.user_id,
            data=body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get(
    "",
    response_model=MeetingListResponse,
    summary="Danh sách cuộc họp",
)
async def danh_sach_cuoc_hop(
    request: Request,
    _: None = Depends(require_auth),
    trang: int = Query(default=1, ge=1, description="Trang hiện tại"),
    kich_thuoc: int = Query(default=20, ge=1, le=100, description="Số mục mỗi trang"),
    trang_thai: Optional[str] = Query(
        default=None,
        description="Lọc theo trạng thái: pending | evaluating | ready | rescheduled | cancelled",
    ),
):
    """Lấy danh sách cuộc họp của user hiện tại, có phân trang và lọc theo trạng thái."""
    try:
        return await meeting_crud_service.list_meetings(
            user_id=request.state.user_id,
            page=trang,
            page_size=kich_thuoc,
            status_filter=trang_thai,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get(
    "/{meeting_id}",
    response_model=MeetingResponse,
    summary="Chi tiết cuộc họp",
)
async def chi_tiet_cuoc_hop(
    meeting_id: str,
    request: Request,
    _: None = Depends(require_auth),
):
    """Lấy thông tin chi tiết của một cuộc họp theo ID."""
    try:
        return await meeting_crud_service.get_by_id(
            user_id=request.state.user_id,
            meeting_id=meeting_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.patch(
    "/{meeting_id}",
    response_model=MeetingResponse,
    summary="Cập nhật cuộc họp",
)
async def cap_nhat_cuoc_hop(
    meeting_id: str,
    body: MeetingUpdate,
    request: Request,
    _: None = Depends(require_auth),
):
    """Cập nhật thông tin cuộc họp. Chỉ cần gửi lên những trường muốn thay đổi."""
    try:
        return await meeting_crud_service.update(
            user_id=request.state.user_id,
            meeting_id=meeting_id,
            data=body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.delete(
    "/{meeting_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Xóa cuộc họp",
)
async def xoa_cuoc_hop(
    meeting_id: str,
    request: Request,
    _: None = Depends(require_auth),
):
    """Xóa cuộc họp. Tất cả tài liệu và lịch sử đánh giá sẽ bị xóa theo (cascade)."""
    try:
        await meeting_crud_service.delete(
            user_id=request.state.user_id,
            meeting_id=meeting_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post(
    "/{meeting_id}/danh-gia",
    summary="Kích hoạt AI đánh giá cuộc họp",
    description=(
        "Gửi cuộc họp vào pipeline AI (LangGraph + Z3). "
        "AI sẽ phân tích điều kiện và trả về READY hoặc RESCHEDULED."
    ),
)
async def danh_gia_ai(
    meeting_id: str,
    request: Request,
    _: None = Depends(require_auth),
    override_facts: Optional[dict] = None,
):
    """
    Trigger AI evaluation cho cuộc họp.

    Body (optional): JSON object ghi đè facts, ví dụ:
    ```json
    {"Slide_Done": true, "Manager_Free": false}
    ```
    """
    try:
        result = await meeting_crud_service.trigger_ai_evaluation(
            user_id=request.state.user_id,
            meeting_id=meeting_id,
            override_facts=override_facts,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get(
    "/{meeting_id}/lich-su-danh-gia",
    summary="Lịch sử AI đánh giá",
)
async def lich_su_danh_gia(
    meeting_id: str,
    request: Request,
    _: None = Depends(require_auth),
    gioi_han: int = Query(default=10, ge=1, le=50, description="Số bản ghi tối đa"),
):
    """Lấy lịch sử toàn bộ lần AI đánh giá cuộc họp, mới nhất lên trước."""
    from integrations.supabase_client import get_supabase

    user_id = request.state.user_id
    supabase = await get_supabase()

    try:
        # Kiểm tra quyền sở hữu trước
        await meeting_crud_service.get_by_id(user_id, meeting_id)

        result = (
            await supabase.table("evaluation_records")
            .select("*")
            .eq("meeting_id", meeting_id)
            .order("evaluated_at", desc=True)
            .limit(gioi_han)
            .execute()
        )

        return {
            "meeting_id": meeting_id,
            "total": len(result.data or []),
            "records": result.data or [],
        }

    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        logger.error(f"Lỗi lấy lịch sử đánh giá: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể lấy lịch sử đánh giá.",
        )
