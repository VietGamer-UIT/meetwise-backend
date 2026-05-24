"""
integrations/supabase_client.py — Supabase Async Client

Cung cấp:
  - get_supabase(): AsyncClient cho backend (service_role, bypass RLS)
  - Lazy singleton — khởi tạo 1 lần, tái sử dụng

Lưu ý bảo mật:
  - Backend dùng SUPABASE_SERVICE_ROLE_KEY (bypass RLS)
  - Frontend dùng SUPABASE_ANON_KEY (tuân theo RLS)
  - KHÔNG bao giờ expose service_role_key ra client
"""

from typing import Optional
from core.logging import get_logger

logger = get_logger(__name__)

# Lazy singleton — khởi tạo khi lần đầu được gọi
_client = None


async def get_supabase():
    """
    Trả về Supabase AsyncClient (lazy singleton).

    Dùng service_role_key để bypass RLS — chỉ dùng ở backend.

    Returns:
        AsyncClient: Supabase client đã khởi tạo.

    Raises:
        RuntimeError: Nếu SUPABASE_URL hoặc SUPABASE_SERVICE_ROLE_KEY chưa cấu hình.
    """
    global _client
    if _client is not None:
        return _client

    from core.config import settings

    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError(
            "Supabase chưa được cấu hình. "
            "Vui lòng set SUPABASE_URL và SUPABASE_SERVICE_ROLE_KEY trong .env"
        )

    try:
        from supabase import create_async_client  # type: ignore
        _client = await create_async_client(
            supabase_url=settings.supabase_url,
            supabase_key=settings.supabase_service_role_key,
        )
        logger.info(
            "Supabase client đã kết nối thành công",
            extra={"event": "supabase_connected", "url": settings.supabase_url},
        )
        return _client
    except ImportError:
        raise RuntimeError(
            "Thư viện supabase chưa được cài. "
            "Chạy: pip install supabase"
        )
    except Exception as exc:
        logger.error(
            f"Không thể kết nối Supabase: {exc}",
            extra={"event": "supabase_connect_error"},
        )
        raise


def reset_client() -> None:
    """
    Reset singleton client (dùng trong tests).
    Gọi hàm này để force re-init client với config mới.
    """
    global _client
    _client = None
