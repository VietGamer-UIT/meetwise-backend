"""
main.py — FastAPI Application Entry Point

MeetWise Backend: Meeting Readiness Evaluation Engine

Architecture Notes:
  • lifespan: startup tasks (graph pre-compile, background cleanup)
    và shutdown tasks (cleanup task cancel, http client close, metrics log).
  • exception_handlers: Token-based trace ID để không rò rỉ context.
  • cleanup_background: awaitable async loop, không blocking.
  • get_status: gọi đúng firestore_client.get_status() (không phải get_meeting_status).
"""

import asyncio
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.v1.meetings import router as meetings_router
from core.config import settings
from core.logging import get_logger
from core.metrics import metrics
from core.trace import generate_trace_id, set_trace_id, reset_trace_id
from schemas.response import ErrorCode, ErrorDetail, ErrorResponse

logger = get_logger(__name__)

# Set module-level để giữ strong reference → ngăn GC "giết" tasks
_background_tasks: set = set()


# ─────────────────────────────────────────────
# Lifespan (startup + shutdown)
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup và shutdown lifecycle tasks."""

    # ── Startup ──────────────────────────────
    logger.info(
        "🚀 MeetWise Backend đang khởi động...",
        extra={"event": "startup", "env": settings.app_env},
    )

    # Warm-up: compile LangGraph trước để tránh cold start latency
    try:
        from agent.graph import get_compiled_graph
        get_compiled_graph()
        logger.info(
            "✅ LangGraph compiled thành công",
            extra={"event": "graph_ready"},
        )
    except Exception as exc:
        logger.warning(
            f"⚠️ LangGraph compile warning: {exc}",
            extra={"event": "graph_compile_warning"},
        )

    # Background task: cleanup rate limiter + idempotency cache định kỳ
    cleanup_task = asyncio.create_task(_cleanup_background())
    _background_tasks.add(cleanup_task)
    cleanup_task.add_done_callback(_background_tasks.discard)

    logger.info(
        "✅ MeetWise Backend sẵn sàng phục vụ",
        extra={
            "event": "startup_complete",
            "host": settings.app_host,
            "port": settings.app_port,
        },
    )

    yield  # Server đang chạy

    # ── Shutdown ──────────────────────────────
    logger.info(
        "🛑 MeetWise Backend đang tắt...",
        extra={"event": "shutdown"},
    )

    # Hủy cleanup task
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    # Đóng HTTP client (giải phóng socket pool)
    try:
        from integrations.google_workspace import close_http_client
        await close_http_client()
    except Exception as exc:
        logger.warning(f"Shutdown: close_http_client fail: {exc}")

    # Log metrics summary khi tắt
    summary = metrics.get_summary()
    logger.info(
        "📊 Metrics summary khi shutdown",
        extra={"event": "metrics_summary", **summary},
    )


async def _cleanup_background() -> None:
    """
    Background task dọn dẹp rate limiter và idempotency cache định kỳ.

    Chạy vô hạn (bị cancel khi shutdown). Dùng asyncio.sleep để không
    block event loop — fully cooperative.
    """
    from services.rate_limiter import rate_limiter
    from services.idempotency import idempotency_cache

    while True:
        await asyncio.sleep(60)  # Chạy mỗi 60 giây

        try:
            rate_limiter.cleanup()
            expired_count = await idempotency_cache.cleanup_expired()
            logger.info(
                "Background cleanup hoàn thành",
                extra={
                    "event": "background_cleanup",
                    "expired_cache_entries": expired_count,
                },
            )
        except Exception as exc:
            # Không để cleanup lỗi crash background task
            logger.warning(
                f"Background cleanup lỗi (non-critical): {exc}",
                extra={"event": "background_cleanup_error"},
            )


# ─────────────────────────────────────────────
# Application Factory
# ─────────────────────────────────────────────

def create_app() -> FastAPI:
    """Tạo FastAPI application với đầy đủ middleware và routes."""

    app = FastAPI(
        title="MeetWise API",
        description=(
            "## Meeting Readiness Evaluation Engine\n\n"
            "Backend service đánh giá sự sẵn sàng của cuộc họp "
            "sử dụng kiến trúc Neuro-Symbolic (LLM optional + Z3 Solver + LangGraph).\n\n"
            "**Zero-Setup**: Chạy được ngay không cần API key hay config.\n"
            "**Frontend**: Đọc API contract tại `/docs` rồi gọi đúng endpoint."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        contact={
            "name": "MeetWise Team",
            "email": "thuhuyen19082005@gmail.com",
        },
        license_info={"name": "MIT"},
    )

    # ── CORS ─────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Trace-ID"],
    )

    # ── Exception Handlers ───────────────────

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """Xử lý Pydantic validation errors → 400. Token-based trace ID."""
        trace_id = generate_trace_id()
        token = set_trace_id(trace_id)
        try:
            errors = []
            for error in exc.errors():
                loc = " → ".join(str(l) for l in error["loc"] if l != "body")
                msg = error["msg"]
                errors.append(f"{loc}: {msg}" if loc else msg)

            message = "; ".join(errors)

            logger.warning(
                "Validation error",
                extra={"event": "validation_error", "errors": errors},
            )

            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error=ErrorDetail(
                        code=ErrorCode.VALIDATION_ERROR,
                        message=message,
                    ),
                    trace_id=trace_id,
                ).model_dump(),
            )
        finally:
            reset_trace_id(token)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        """Xử lý HTTP errors (404, 405, v.v.) theo schema chuẩn."""
        trace_id = generate_trace_id()
        token = set_trace_id(trace_id)
        try:
            return JSONResponse(
                status_code=exc.status_code,
                content=ErrorResponse(
                    error=ErrorDetail(
                        code="HTTP_ERROR",
                        message=str(exc.detail),
                    ),
                    trace_id=trace_id,
                ).model_dump(),
            )
        finally:
            reset_trace_id(token)

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Xử lý unhandled exceptions — log server-side, trả 500 không có stacktrace."""
        trace_id = generate_trace_id()
        token = set_trace_id(trace_id)
        try:
            logger.error(
                f"Unhandled exception: {exc}",
                extra={"event": "unhandled_exception"},
                exc_info=True,
            )
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=ErrorResponse(
                    error=ErrorDetail(
                        code=ErrorCode.INTERNAL_ERROR,
                        message="Lỗi nội bộ hệ thống. Vui lòng thử lại sau.",
                    ),
                    trace_id=trace_id,
                ).model_dump(),
            )
        finally:
            reset_trace_id(token)

    # ── Routes ───────────────────────────────
    app.include_router(meetings_router)

    # ── Health Check ─────────────────────────
    @app.get(
        "/health",
        tags=["system"],
        summary="Health check",
    )
    async def health_check() -> dict:
        """Kiểm tra service có đang hoạt động không."""
        return {
            "status": "healthy",
            "service": "meetwise-backend",
            "environment": settings.app_env,
            "mode": {
                "use_llm": settings.use_llm,
                "use_firebase": settings.use_firebase,
                "use_google_services": settings.use_google_services,
            },
            "metrics": metrics.get_summary(),
        }

    # ── Metrics Endpoint ─────────────────────
    @app.get(
        "/metrics",
        tags=["system"],
        summary="Service metrics",
        include_in_schema=not settings.is_production,
    )
    async def get_metrics() -> dict:
        """Lấy metrics hiện tại của service (ẩn trong production)."""
        return metrics.get_summary()

    # ── Meeting Status Endpoint ───────────────
    @app.get(
        "/v1/meetings/{meeting_id}/status",
        tags=["meetings"],
        summary="Lấy trạng thái lifecycle của cuộc họp",
    )
    async def get_status(meeting_id: str) -> dict:
        """
        Lấy lifecycle status của một cuộc họp từ Firestore.

        Status: Pending | Processing | Ready | Unsat

        Note: Gọi đúng `get_meeting_status()` — không phải `get_status()`.
        """
        import re

        if not re.match(r"^[a-zA-Z0-9_-]+$", meeting_id) or len(meeting_id) > 100:
            return {"error": "meeting_id không hợp lệ"}

        from storage.firestore_client import firestore_client

        status_data = await firestore_client.get_meeting_status(meeting_id)
        if status_data is None:
            return {
                "meeting_id": meeting_id,
                "lifecycle_status": "Pending",
                "message": "Cuộc họp chưa được đánh giá",
            }
        return {"meeting_id": meeting_id, **status_data}

    return app


# ─────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────

app = create_app()

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", settings.app_port))

    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=port,
        reload=not settings.is_production,
        log_level=settings.log_level.lower(),
        access_log=True,
    )
