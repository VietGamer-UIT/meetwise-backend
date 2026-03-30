"""
api/v1/meetings.py — POST /v1/meetings/evaluate Router

Xử lý:
1. Validate headers (X-Request-ID, Authorization)
2. Rate limiting theo IP
3. Check idempotency cache
4. Sanitize input
5. Chạy LangGraph pipeline (với overall timeout)
6. Return response không expose stack trace
"""

import time
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from agent.graph import get_compiled_graph
from agent.state import MeetingState
from core.config import settings
from core.logging import get_logger, log_request
from core.metrics import metrics
from core.trace import generate_trace_id, set_trace_id, get_trace_id
from schemas.request import EvaluateRequest
from schemas.response import (
    ErrorCode,
    ErrorDetail,
    ErrorResponse,
    EvaluateResponse,
    MeetingStatus,
)
from services.idempotency import idempotency_cache
from services.rate_limiter import rate_limiter
from services.sanitizer import sanitize_rule, sanitize_meeting_id
import asyncio

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/meetings", tags=["meetings"])


# ─────────────────────────────────────────────
# Helper: Error Response Builder
# ─────────────────────────────────────────────

def _error_response(
    code: str,
    message: str,
    trace_id: str,
    http_status: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
) -> JSONResponse:
    """Tạo error response chuẩn — không expose stack trace."""
    return JSONResponse(
        status_code=http_status,
        content=ErrorResponse(
            error=ErrorDetail(code=code, message=message),
            trace_id=trace_id,
        ).model_dump(),
    )


# ─────────────────────────────────────────────
# POST /v1/meetings/evaluate
# ─────────────────────────────────────────────

@router.post(
    "/evaluate",
    response_model=EvaluateResponse,
    responses={
        200: {"description": "Đánh giá thành công"},
        400: {"model": ErrorResponse, "description": "Request không hợp lệ"},
        429: {"model": ErrorResponse, "description": "Rate limit vượt ngưỡng"},
        500: {"model": ErrorResponse, "description": "Lỗi hệ thống"},
        503: {"model": ErrorResponse, "description": "LLM không phản hồi"},
    },
    summary="Đánh giá sự sẵn sàng của cuộc họp",
    description=(
        "Nhận rule điều kiện cuộc họp và facts, "
        "sử dụng LLM + Z3 solver để quyết định READY hoặc RESCHEDULED."
    ),
)
async def evaluate_meeting(
    request: Request,
    body: EvaluateRequest,
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-ID"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    POST /v1/meetings/evaluate

    Đánh giá xem cuộc họp có đủ điều kiện diễn ra không.
    """
    request_start = time.perf_counter()

    # ─── 1. Trace ID ─────────────────────────────
    trace_id = x_request_id or generate_trace_id()
    set_trace_id(trace_id)

    logger.info(
        "Request mới nhận được",
        extra={
            "event": "request_received",
            "meeting_id": body.meeting_id,
            "trace_id": trace_id,
            "has_facts_override": body.facts is not None,
        },
    )

    # ─── 2. Rate limiting ────────────────────────
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(client_ip):
        remaining = rate_limiter.get_remaining(client_ip)
        return _error_response(
            code=ErrorCode.RATE_LIMIT_EXCEEDED,
            message=(
                f"Quá nhiều requests. Giới hạn: {settings.rate_limit_max_requests} "
                f"requests/{settings.rate_limit_window_seconds}s. "
                f"Vui lòng thử lại sau."
            ),
            trace_id=trace_id,
            http_status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    # ─── 3. Sanitize input ───────────────────────
    try:
        sanitized_rule = sanitize_rule(body.rule)
        sanitized_meeting_id = sanitize_meeting_id(body.meeting_id)
    except ValueError as exc:
        return _error_response(
            code=ErrorCode.VALIDATION_ERROR,
            message=str(exc),
            trace_id=trace_id,
            http_status=status.HTTP_400_BAD_REQUEST,
        )

    # ─── 4. Idempotency check ────────────────────
    # 4a. Kiểm tra cache
    cached = await idempotency_cache.get_cached(sanitized_meeting_id)
    if cached is not None:
        logger.info(
            "Trả về kết quả từ idempotency cache",
            extra={"event": "cache_return", "meeting_id": sanitized_meeting_id},
        )
        return JSONResponse(content=cached)

    # 4b. Kiểm tra có đang xử lý không
    is_processing = await idempotency_cache.is_processing(sanitized_meeting_id)
    if is_processing:
        logger.info(
            "Meeting đang được xử lý, chờ kết quả",
            extra={"event": "wait_processing", "meeting_id": sanitized_meeting_id},
        )
        waited_result = await idempotency_cache.wait_for_result(
            sanitized_meeting_id,
            timeout=settings.request_timeout_seconds,
        )
        if waited_result is not None:
            return JSONResponse(content=waited_result)
        # Timeout khi chờ → trả về lỗi
        return _error_response(
            code=ErrorCode.TIMEOUT,
            message="Timeout khi chờ xử lý. Vui lòng thử lại.",
            trace_id=trace_id,
            http_status=status.HTTP_408_REQUEST_TIMEOUT,
        )

    # 4c. Acquire lock và bắt đầu xử lý
    acquired = await idempotency_cache.acquire_lock(sanitized_meeting_id)
    if not acquired:
        # Race condition: vừa lock được bởi request khác
        waited_result = await idempotency_cache.wait_for_result(sanitized_meeting_id)
        if waited_result is not None:
            return JSONResponse(content=waited_result)

    # ─── 5. Chạy LangGraph Pipeline ─────────────
    try:
        initial_state: MeetingState = {
            "trace_id": trace_id,
            "meeting_id": sanitized_meeting_id,
            "request_start_time": request_start,
            "raw_rule": sanitized_rule,
            "raw_facts": body.facts,
            "step_latencies": {},
        }

        graph = get_compiled_graph()

        # Chạy pipeline với overall timeout
        final_state = await asyncio.wait_for(
            graph.ainvoke(initial_state),
            timeout=settings.request_timeout_seconds,
        )

        # ─── 6. Xử lý kết quả ───────────────────
        total_latency_ms = round(
            (time.perf_counter() - request_start) * 1000, 2
        )

        # Kiểm tra error trong state
        if final_state.get("error_code"):
            error_code = final_state["error_code"]
            error_message = final_state.get("error_message", "Lỗi không xác định")

            await idempotency_cache.release_lock_on_error(sanitized_meeting_id)

            http_status_map = {
                ErrorCode.BAD_REQUEST: status.HTTP_400_BAD_REQUEST,
                ErrorCode.VALIDATION_ERROR: status.HTTP_400_BAD_REQUEST,
                ErrorCode.LLM_PARSE_ERROR: status.HTTP_400_BAD_REQUEST,
                ErrorCode.LLM_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
                ErrorCode.TIMEOUT: status.HTTP_408_REQUEST_TIMEOUT,
                ErrorCode.INTERNAL_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
            }
            http_status_code = http_status_map.get(
                error_code, status.HTTP_500_INTERNAL_SERVER_ERROR
            )

            metrics.record_request(success=False, latency_ms=total_latency_ms)

            return _error_response(
                code=error_code,
                message=error_message,
                trace_id=trace_id,
                http_status=http_status_code,
            )

        # Thành công → build response
        from schemas.response import ActionResult

        # Deserialize executed_actions từ state (list of dicts)
        raw_actions = final_state.get("executed_actions") or []
        actions = []
        for a in raw_actions:
            try:
                actions.append(ActionResult(**a))
            except Exception:
                pass  # Bỏ qua action nếu deserialize lỗi

        response_data = EvaluateResponse(
            trace_id=trace_id,
            meeting_id=sanitized_meeting_id,
            status=MeetingStatus(final_state.get("final_status", MeetingStatus.RESCHEDULED)),
            reason=final_state.get("final_reason", ""),
            unsatisfied_conditions=final_state.get("unsatisfied_conditions") or [],
            actions=actions,
            latency_ms=total_latency_ms,
        )

        response_dict = response_data.model_dump()

        # Cache kết quả thành công
        await idempotency_cache.release_lock(sanitized_meeting_id, response_dict)

        metrics.record_request(success=True, latency_ms=total_latency_ms)
        log_request(
            logger,
            meeting_id=sanitized_meeting_id,
            status=response_data.status.value,
            latency_ms=total_latency_ms,
        )

        return JSONResponse(content=response_dict)

    except asyncio.TimeoutError:
        await idempotency_cache.release_lock_on_error(sanitized_meeting_id)
        total_latency_ms = round((time.perf_counter() - request_start) * 1000, 2)
        metrics.record_request(success=False, latency_ms=total_latency_ms)

        logger.error(
            "Request timeout toàn cục",
            extra={
                "event": "request_timeout",
                "meeting_id": sanitized_meeting_id,
                "latency_ms": total_latency_ms,
            },
        )
        return _error_response(
            code=ErrorCode.TIMEOUT,
            message=f"Request timeout sau {settings.request_timeout_seconds}s. Vui lòng thử lại.",
            trace_id=trace_id,
            http_status=status.HTTP_408_REQUEST_TIMEOUT,
        )

    except Exception as exc:
        await idempotency_cache.release_lock_on_error(sanitized_meeting_id)
        total_latency_ms = round((time.perf_counter() - request_start) * 1000, 2)
        metrics.record_request(success=False, latency_ms=total_latency_ms)

        # Log chi tiết để debug nhưng KHÔNG expose cho client
        logger.error(
            "Lỗi không mong đợi",
            extra={
                "event": "unexpected_error",
                "meeting_id": sanitized_meeting_id,
                "error_type": type(exc).__name__,
                # Không log exc str đầy đủ vào response, chỉ log internal
            },
            exc_info=True,
        )
        return _error_response(
            code=ErrorCode.INTERNAL_ERROR,
            message="Hệ thống gặp lỗi không xác định. Vui lòng thử lại sau hoặc liên hệ support.",
            trace_id=trace_id,
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
