"""
middleware/auth_middleware.py — JWT Authentication Middleware

Verify Supabase JWT token, inject user_id vào request.state.

Xử lý đầy đủ các edge cases:
  - Token expired → 401
  - Token invalid signature → 401
  - Token missing → 401
  - Supabase JWT secret chưa cấu hình → 503

Pattern sử dụng:
    from middleware.auth_middleware import require_auth

    @router.get("/protected")
    async def handler(
        request: Request,
        _: None = Depends(require_auth),
    ):
        user_id = request.state.user_id  # inject bởi middleware

Lưu ý Supabase JWT:
  - Supabase không set 'aud' claim theo chuẩn RFC 7519
  → Phải dùng options={"verify_aud": False} trong python-jose
"""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

# HTTPBearer scheme — tự động extract token từ header "Authorization: Bearer <token>"
_bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """
    FastAPI dependency để bảo vệ endpoint.

    Verify Supabase JWT và inject user_id vào request.state.

    Usage:
        @router.get("/endpoint")
        async def handler(
            request: Request,
            _: None = Depends(require_auth),
        ):
            user_id = request.state.user_id

    Raises:
        HTTPException 401: Token thiếu hoặc không hợp lệ.
        HTTPException 503: Supabase JWT secret chưa cấu hình.
    """
    # Kiểm tra token có trong header không
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Yêu cầu xác thực. Vui lòng đăng nhập.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Kiểm tra Supabase JWT secret đã cấu hình chưa
    if not settings.supabase_jwt_secret:
        logger.error(
            "SUPABASE_JWT_SECRET chưa được cấu hình",
            extra={"event": "jwt_secret_missing"},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hệ thống xác thực chưa sẵn sàng. Vui lòng liên hệ quản trị viên.",
        )

    token = credentials.credentials

    try:
        from jose import JWTError, jwt  # type: ignore

        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={
                "verify_aud": False,   # Supabase không set aud theo chuẩn
                "verify_iss": False,   # Bỏ qua issuer verification
            },
        )

        user_id: str | None = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token không hợp lệ: thiếu thông tin người dùng.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Inject vào request.state để endpoints có thể lấy
        request.state.user_id = user_id
        request.state.user_email = payload.get("email", "")
        request.state.user_role = payload.get("role", "authenticated")

        logger.debug(
            f"Auth thành công: user_id={user_id[:8]}...",
            extra={"event": "auth_success", "user_id": user_id},
        )

    except ImportError:
        raise RuntimeError(
            "Thư viện python-jose chưa được cài. "
            "Chạy: pip install python-jose[cryptography]"
        )
    except Exception as exc:
        exc_str = str(exc).lower()
        # Phân biệt các loại lỗi JWT để log chính xác
        if "expired" in exc_str:
            error_detail = "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."
            logger.info(
                "JWT token đã hết hạn",
                extra={"event": "jwt_expired"},
            )
        elif "signature" in exc_str or "invalid" in exc_str:
            error_detail = "Token không hợp lệ. Vui lòng đăng nhập lại."
            logger.warning(
                f"JWT signature không hợp lệ: {exc}",
                extra={"event": "jwt_invalid_signature"},
            )
        else:
            error_detail = "Xác thực thất bại. Vui lòng thử lại."
            logger.error(
                f"JWT verify lỗi: {exc}",
                extra={"event": "jwt_error", "error": str(exc)},
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str | None:
    """
    Dependency tùy chọn — không bắt buộc auth.
    Trả về user_id nếu có token hợp lệ, None nếu không có.
    Dùng cho endpoints public nhưng cần biết user nếu đã đăng nhập.
    """
    if credentials is None:
        return None
    try:
        await require_auth(request, credentials)
        return request.state.user_id
    except HTTPException:
        return None
