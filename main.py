"""
main.py — FastAPI Application Entry Point

MeetWise Backend: Meeting Readiness Evaluation Engine
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
from core.trace import generate_trace_id, set_trace_id
from schemas.response import ErrorCode, ErrorDetail, ErrorResponse

logger = get_logger(__name__)

background_tasks = set()


# ─────────────────────────────────────────────
# Lifespan (startup + shutdown)
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup và shutdown tasks."""

    # ── Startup ──────────────────────────────
    logger.info(
        "🚀 MeetWise Backend đang khởi động...",
        extra={"event": "startup", "env": settings.app_env},
    )

    # Warm-up: compile LangGraph trước (tránh cold start)
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
    background_tasks.add(cleanup_task)
    cleanup_task.add_done_callback(background_tasks.discard)

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
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    # Log metrics summary khi tắt
    summary = metrics.get_summary()
    logger.info(
        "📊 Metrics summary",
        extra={"event": "metrics_summary", **summary},
    )


async def _cleanup_background() -> None:
    """Background task dọn dẹp rate limiter và cache định kỳ."""
    from services.rate_limiter import rate_limiter
    from services.idempotency import idempotency_cache

    while True:
        await asyncio.sleep(60)  # Chạy mỗi 60 giây
        rate_limiter.cleanup()
        await idempotency_cache.cleanup_expired()
        logger.info(
            "Background cleanup hoàn thành",
            extra={"event": "background_cleanup"},
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
        # Swagger luôn bật — FE cần đọc contract
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        contact={
            "name": "MeetWise Team",
            "email": "thuhuyen19082005@gmail.com",
        },
        license_info={
            "name": "MIT",
        },
    )

    # ── CORS ─────────────────────────────────
    # Frontend có thể gọi được backend — cấu hình qua CORS_ALLOWED_ORIGINS
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
        """Xử lý Pydantic validation errors → 400."""
        trace_id = generate_trace_id()
        set_trace_id(trace_id)

        # Build friendly error messages
        errors = []
        for error in exc.errors():
            loc = " → ".join(str(l) for l in error["loc"] if l != "body")
            msg = error["msg"]
            errors.append(f"{loc}: {msg}" if loc else msg)

        message = "; ".join(errors)

        logger.warning(
            "Validation error",
            extra={
                "event": "validation_error",
                "errors": errors,
            },
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

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        """Xử lý HTTP errors (ví dụ 404, 405) theo chuẩn schema."""
        trace_id = generate_trace_id()
        set_trace_id(trace_id)
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

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        import traceback
        print("🔥 REAL ERROR:", exc)
        print(traceback.format_exc())

        from fastapi import HTTPException
        raise HTTPException(
            status_code=500,
            detail=str(exc)  # trả lỗi thật ra ngoài
        )

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
        summary = metrics.get_summary()
        return {
            "status": "healthy",
            "service": "meetwise-backend",
            "environment": settings.app_env,
            "mode": {
                "use_llm": settings.use_llm,
                "use_firebase": settings.use_firebase,
                "use_google_services": settings.use_google_services,
            },
            "metrics": summary,
        }

    # ── Metrics Endpoint ─────────────────────
    @app.get(
        "/metrics",
        tags=["system"],
        summary="Service metrics",
        include_in_schema=not settings.is_production,
    )
    async def get_metrics() -> dict:
        """Lấy metrics hiện tại của service."""
        return metrics.get_summary()

    # ── Meeting Status Endpoint ────────────────
    @app.get(
        "/v1/meetings/{meeting_id}/status",
        tags=["meetings"],
        summary="Lấy trạng thái cuộc họỹ từ storage",
    )
    async def get_meeting_status(meeting_id: str) -> dict:
        """
        Lấy lifecycle status của một cuộc họỹ.
        Status: Pending | Processing | Ready | Unsat
        """
        from storage.firestore_client import firestore_client
        import re

        # Basic validation
        if not re.match(r'^[a-zA-Z0-9_-]+$', meeting_id) or len(meeting_id) > 100:
            return {"error": "meeting_id không hợp lệ"}

        status_data = await firestore_client.get_meeting_status(meeting_id)
        if status_data is None:
            return {
                "meeting_id": meeting_id,
                "lifecycle_status": "Pending",
                "message": "Cuộc họỹ chưa được đánh giá",
            }
        return {"meeting_id": meeting_id, **status_data}

    return app


# ─────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────

app = create_app()

if __name__ == "__main__":
    import uvicorn

    # Cloud Run injects PORT env var
    port = int(os.environ.get("PORT", settings.app_port))

    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=port,
        reload=not settings.is_production,
        log_level=settings.log_level.lower(),
        access_log=True,
    )
