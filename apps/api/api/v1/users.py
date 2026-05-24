"""
api/v1/users.py — User Profile Endpoints

Endpoints:
  GET   /v1/users/ho-so         — Lấy hồ sơ cá nhân
  PATCH /v1/users/ho-so         — Cập nhật hồ sơ cá nhân
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from core.logging import get_logger
from middleware.auth_middleware import require_auth
from models.user import UserProfileResponse, UserProfileUpdate

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/users", tags=["👤 Người dùng"])


@router.get(
    "/ho-so",
    response_model=UserProfileResponse,
    summary="Lấy hồ sơ cá nhân",
)
async def lay_ho_so(
    request: Request,
    _: None = Depends(require_auth),
):
    """Trả về thông tin hồ sơ của user đang đăng nhập."""
    from integrations.supabase_client import get_supabase

    user_id = request.state.user_id
    supabase = await get_supabase()

    try:
        result = (
            await supabase.table("user_profiles")
            .select("*")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Hồ sơ không tìm thấy.",
            )

        profile = result.data
        return UserProfileResponse(
            id=profile["id"],
            email=request.state.user_email or "",
            full_name=profile.get("full_name"),
            organization=profile.get("organization"),
            job_title=profile.get("job_title"),
            avatar_url=profile.get("avatar_url"),
            timezone=profile.get("timezone", "Asia/Ho_Chi_Minh"),
            language=profile.get("language", "vi"),
            created_at=profile["created_at"],
            updated_at=profile["updated_at"],
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Lỗi lấy hồ sơ: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể lấy hồ sơ.",
        )


@router.patch(
    "/ho-so",
    response_model=UserProfileResponse,
    summary="Cập nhật hồ sơ cá nhân",
)
async def cap_nhat_ho_so(
    body: UserProfileUpdate,
    request: Request,
    _: None = Depends(require_auth),
):
    """Cập nhật các trường hồ sơ (chỉ cập nhật những trường được gửi lên)."""
    from integrations.supabase_client import get_supabase

    user_id = request.state.user_id
    supabase = await get_supabase()

    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không có dữ liệu để cập nhật.",
        )

    try:
        result = (
            await supabase.table("user_profiles")
            .update(update_data)
            .eq("id", user_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy hồ sơ để cập nhật.",
            )

        profile = result.data[0]
        logger.info(
            "Hồ sơ cập nhật",
            extra={"event": "profile_updated", "user_id": user_id, "fields": list(update_data.keys())},
        )

        return UserProfileResponse(
            id=profile["id"],
            email=request.state.user_email or "",
            full_name=profile.get("full_name"),
            organization=profile.get("organization"),
            job_title=profile.get("job_title"),
            avatar_url=profile.get("avatar_url"),
            timezone=profile.get("timezone", "Asia/Ho_Chi_Minh"),
            language=profile.get("language", "vi"),
            created_at=profile["created_at"],
            updated_at=profile["updated_at"],
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Lỗi cập nhật hồ sơ: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể cập nhật hồ sơ.",
        )
