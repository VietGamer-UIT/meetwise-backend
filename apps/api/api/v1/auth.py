"""
api/v1/auth.py — Authentication Endpoints

Tất cả auth logic đều delegate sang Supabase Auth.
Backend chỉ verify token và trả về thông tin user.

Endpoints:
  POST /v1/auth/dang-ky         — Đăng ký tài khoản mới
  POST /v1/auth/dang-nhap       — Đăng nhập
  POST /v1/auth/dang-xuat       — Đăng xuất (invalidate session)
  POST /v1/auth/lam-moi         — Refresh access token
  GET  /v1/auth/toi             — Thông tin user hiện tại
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from core.logging import get_logger
from middleware.auth_middleware import require_auth

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/auth", tags=["🔐 Xác thực"])


# ─────────────────────────────────────────────
# Request / Response Schemas (inline — auth only)
# ─────────────────────────────────────────────

class DangKyRequest(BaseModel):
    email: EmailStr = Field(..., description="Địa chỉ email")
    password: str = Field(..., min_length=6, description="Mật khẩu (tối thiểu 6 ký tự)")
    full_name: str = Field(..., min_length=1, max_length=100, description="Họ và tên")


class DangNhapRequest(BaseModel):
    email: EmailStr = Field(..., description="Địa chỉ email")
    password: str = Field(..., min_length=1, description="Mật khẩu")


class LamMoiRequest(BaseModel):
    refresh_token: str = Field(..., description="Refresh token từ lần đăng nhập trước")


class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserMeResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    organization: str | None
    job_title: str | None
    avatar_url: str | None
    timezone: str
    created_at: str


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@router.post(
    "/dang-ky",
    status_code=status.HTTP_201_CREATED,
    summary="Đăng ký tài khoản mới",
    response_model=AuthTokenResponse,
)
async def dang_ky(body: DangKyRequest):
    """
    Tạo tài khoản mới qua Supabase Auth.
    Tự động tạo user_profile với full_name.
    """
    from integrations.supabase_client import get_supabase

    supabase = await get_supabase()

    try:
        result = await supabase.auth.sign_up({
            "email": body.email,
            "password": body.password,
            "options": {
                "data": {"full_name": body.full_name}
            },
        })

        if not result.session:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Đăng ký thành công. Vui lòng kiểm tra email để xác nhận tài khoản.",
            )

        logger.info(
            "Tài khoản mới đăng ký",
            extra={"event": "user_registered", "email": body.email},
        )

        return AuthTokenResponse(
            access_token=result.session.access_token,
            refresh_token=result.session.refresh_token,
            expires_in=result.session.expires_in or 3600,
        )

    except HTTPException:
        raise
    except Exception as exc:
        exc_str = str(exc).lower()
        if "already registered" in exc_str or "already exists" in exc_str:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email này đã được đăng ký. Vui lòng đăng nhập.",
            )
        logger.error(f"Lỗi đăng ký: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đăng ký thất bại. Vui lòng thử lại.",
        )


@router.post(
    "/dang-nhap",
    summary="Đăng nhập",
    response_model=AuthTokenResponse,
)
async def dang_nhap(body: DangNhapRequest):
    """Đăng nhập bằng email/mật khẩu. Trả về access_token + refresh_token."""
    from integrations.supabase_client import get_supabase

    supabase = await get_supabase()

    try:
        result = await supabase.auth.sign_in_with_password({
            "email": body.email,
            "password": body.password,
        })

        if not result.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email hoặc mật khẩu không đúng.",
            )

        logger.info(
            "Đăng nhập thành công",
            extra={"event": "user_login", "user_id": result.user.id if result.user else "unknown"},
        )

        return AuthTokenResponse(
            access_token=result.session.access_token,
            refresh_token=result.session.refresh_token,
            expires_in=result.session.expires_in or 3600,
        )

    except HTTPException:
        raise
    except Exception as exc:
        exc_str = str(exc).lower()
        if "invalid" in exc_str or "credentials" in exc_str or "password" in exc_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email hoặc mật khẩu không đúng.",
            )
        logger.error(f"Lỗi đăng nhập: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đăng nhập thất bại. Vui lòng thử lại.",
        )


@router.post(
    "/dang-xuat",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Đăng xuất",
)
async def dang_xuat(
    request: Request,
    _: None = Depends(require_auth),
):
    """Invalidate session hiện tại trên Supabase."""
    from integrations.supabase_client import get_supabase

    supabase = await get_supabase()

    try:
        await supabase.auth.sign_out()
        logger.info(
            "Đăng xuất",
            extra={"event": "user_logout", "user_id": request.state.user_id},
        )
    except Exception as exc:
        logger.warning(f"Lỗi đăng xuất (non-critical): {exc}")


@router.post(
    "/lam-moi",
    summary="Làm mới access token",
    response_model=AuthTokenResponse,
)
async def lam_moi_token(body: LamMoiRequest):
    """Dùng refresh_token để lấy access_token mới."""
    from integrations.supabase_client import get_supabase

    supabase = await get_supabase()

    try:
        result = await supabase.auth.refresh_session(body.refresh_token)

        if not result.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token không hợp lệ hoặc đã hết hạn. Vui lòng đăng nhập lại.",
            )

        return AuthTokenResponse(
            access_token=result.session.access_token,
            refresh_token=result.session.refresh_token,
            expires_in=result.session.expires_in or 3600,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Lỗi refresh token: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Không thể làm mới phiên. Vui lòng đăng nhập lại.",
        )


@router.get(
    "/toi",
    summary="Thông tin tài khoản hiện tại",
    response_model=UserMeResponse,
)
async def lay_thong_tin_toi(
    request: Request,
    _: None = Depends(require_auth),
):
    """Trả về thông tin user đang đăng nhập từ user_profiles."""
    from integrations.supabase_client import get_supabase

    user_id = request.state.user_id
    supabase = await get_supabase()

    try:
        # Lấy profile từ bảng user_profiles
        result = await supabase.table("user_profiles").select("*").eq("id", user_id).maybe_single().execute()

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy thông tin tài khoản.",
            )

        profile = result.data
        return UserMeResponse(
            id=profile["id"],
            email=request.state.user_email or "",
            full_name=profile.get("full_name"),
            organization=profile.get("organization"),
            job_title=profile.get("job_title"),
            avatar_url=profile.get("avatar_url"),
            timezone=profile.get("timezone", "Asia/Ho_Chi_Minh"),
            created_at=str(profile.get("created_at", "")),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Lỗi lấy thông tin user: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể lấy thông tin tài khoản.",
        )
