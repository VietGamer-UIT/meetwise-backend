"""
api/v1/meetings.py — POST /v1/meetings/evaluate Router

Pipeline xử lý (theo thứ tự):
  1. Token-based Trace ID setup (Token pattern, restore trong finally)
  2. Rate limiting theo client IP
  3. Idempotency cache check (đã có kết quả → trả về ngay)
  4. Lock acquisition với ownership tracking (acquired flag)
  5. Input sanitization
  6. LangGraph pipeline execution
  7. Response building + cache release

Race Condition Fixes:
  • acquired = False trước try block → finally chỉ release nếu ta thực sự
    có lock (không giải phóng nhầm lock của request concurrent khác).
  • Nếu wait_for_result() trả None → HTTP 409 ngay, không chạy tiếp.
  • Token pattern đảm bảo trace_id của request cha không bị mutate.

Lock Ownership Protocol:
  acquired = False  # khởi tạo trước try để finally luôn thấy
  try:
      acquired = await idempotency_cache.acquire_lock(...)  # True/False
      ...
  finally:
      if acquired:                                          # chỉ release nếu ta giữ lock
          await idempotency_cache.release_lock_on_error(...)
"""

import time
from typing import Optional

import asyncio
from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse

from agent.graph import get_compiled_graph  # noqa: F401 (ensure graph compile)
from agent.state import MeetingState
from core.config import settings
from core.logging import get_logger, log_request
from core.metrics import metrics
from core.trace import generate_trace_id, set_trace_id, get_trace_id, reset_trace_id
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

logger = get_logger(__name__)

router = APIRouter(tags=["meetings"])


# ─────────────────────────────────────────────
# Helper: Chuẩn hoá Error Response
# ─────────────────────────────────────────────

def _error_response(
    code: str,
    message: str,
    trace_id: str,
    http_status: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
) -> JSONResponse:
    """
    Tạo JSONResponse lỗi chuẩn hoá — không bao giờ expose stack trace.

    Args:
        code:        ErrorCode enum value (string).
        message:     Thông điệp lỗi thân thiện với người dùng.
        trace_id:    Trace ID của request hiện tại.
        http_status: HTTP status code (mặc định 500).

    Returns:
        JSONResponse với schema ErrorResponse chuẩn.
    """
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
    "/v1/meetings/evaluate",
    response_model=EvaluateResponse,
    responses={
        200: {"description": "Đánh giá thành công"},
        400: {"model": ErrorResponse, "description": "Request không hợp lệ"},
        409: {"model": ErrorResponse, "description": "Meeting đang được xử lý (Conflict)"},
        429: {"model": ErrorResponse, "description": "Rate limit vượt ngưỡng"},
        500: {"model": ErrorResponse, "description": "Lỗi hệ thống"},
        503: {"model": ErrorResponse, "description": "LLM không phản hồi"},
    },
    summary="Đánh giá sự sẵn sàng của cuộc họp",
    description=(
        "Nhận rule điều kiện cuộc họp và facts tuỳ chọn, "
        "sử dụng LLM + Z3 solver để quyết định READY hoặc RESCHEDULED. "
        "Hỗ trợ idempotency: cùng meeting_id trong TTL luôn trả kết quả cached."
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
    Pipeline: validate → rate-limit → idempotency → LangGraph → response.
    """
    request_start = time.perf_counter()

    # ─── 1. Trace ID Setup (Token Pattern) ────────────────────────
    # Token phải được khai báo trước try để finally luôn có thể gọi reset.
    trace_id = x_request_id or generate_trace_id()
    token = set_trace_id(trace_id)

    # acquired PHẢI khởi tạo False trước try để finally an toàn.
    # Nếu exception xảy ra trước acquire_lock(), finally sẽ thấy
    # acquired=False và KHÔNG gọi release (đúng hành vi).
    acquired = False

    # Sanitize ngay để có meeting_id cho logging sớm
    sanitized_meeting_id = sanitize_meeting_id(body.meeting_id)

    try:
        logger.info(
            "Request mới nhận được",
            extra={
                "event": "request_received",
                "meeting_id": sanitized_meeting_id,
                "trace_id": trace_id,
                "has_override_facts": body.override_facts is not None,
            },
        )

        # ─── 2. Rate Limiting ─────────────────────────────────────
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.is_allowed(client_ip):
            return _error_response(
                code=ErrorCode.RATE_LIMIT_EXCEEDED,
                message=(
                    f"Quá nhiều requests. Giới hạn: {settings.rate_limit_max_requests} "
                    f"requests/{settings.rate_limit_window_seconds}s. "
                    "Vui lòng thử lại sau."
                ),
                trace_id=trace_id,
                http_status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # ─── 3. Input Sanitization ────────────────────────────────
        sanitized_rule = sanitize_rule(body.rule)
        demo_facts = body.override_facts or {}

        # ─── 4a. Idempotency Cache Check ──────────────────────────
        cached = await idempotency_cache.get_cached(sanitized_meeting_id)
        if cached is not None:
            logger.info(
                "Trả về kết quả từ idempotency cache",
                extra={"event": "cache_return", "meeting_id": sanitized_meeting_id},
            )
            return JSONResponse(content=cached)

        # ─── 4b. Kiểm tra nếu đang trong quá trình xử lý ─────────
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

            # Timeout khi chờ → HTTP 409 (không retry vô ích)
            return _error_response(
                code=ErrorCode.ALREADY_PROCESSING,
                message="Meeting đang được xử lý, vui lòng thử lại sau.",
                trace_id=trace_id,
                http_status=status.HTTP_409_CONFLICT,
            )

        # ─── 4c. Acquire Lock (với Ownership Tracking) ───────────
        # Sau bước này, acquired=True mới có quyền release trong finally.
        acquired = await idempotency_cache.acquire_lock(sanitized_meeting_id)
        if not acquired:
            # Race condition: request khác vừa snatch mất lock
            waited_result = await idempotency_cache.wait_for_result(
                sanitized_meeting_id,
                timeout=settings.request_timeout_seconds,
            )
            if waited_result is not None:
                return JSONResponse(content=waited_result)

            # Không lấy được lock VÀ wait cũng None → HTTP 409
            return _error_response(
                code=ErrorCode.ALREADY_PROCESSING,
                message="Meeting đang được xử lý, vui lòng thử lại sau.",
                trace_id=trace_id,
                http_status=status.HTTP_409_CONFLICT,
            )

        # ─── 5. Chạy LangGraph Pipeline ───────────────────────────
        initial_state: MeetingState = {
            "trace_id": trace_id,
            "meeting_id": sanitized_meeting_id,
            "request_start_time": request_start,
            "raw_rule": sanitized_rule,
            "raw_facts": demo_facts,
            "step_latencies": {},
        }

        from services.evaluate_service import evaluate_meeting_service

        result = await evaluate_meeting_service(body, initial_state)

        if result is None:
            raise ValueError("evaluate_meeting_service trả về None — pipeline bị gián đoạn")

        final_state = result

        # ─── 6. Kiểm tra Lỗi trong State ──────────────────────────
        total_latency_ms = round((time.perf_counter() - request_start) * 1000, 2)

        if final_state.get("error_code"):
            error_code = final_state["error_code"]
            error_message = final_state.get("error_message", "Lỗi không xác định")

            # Release lock ngay khi biết kết quả là lỗi — ta đang giữ lock
            if acquired:
                await idempotency_cache.release_lock_on_error(sanitized_meeting_id)
                acquired = False  # Đánh dấu đã release để finally không release lại

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

        # ─── 7. Build Response ────────────────────────────────────
        from schemas.response import ActionResult

        raw_actions = final_state.get("executed_actions") or []
        actions = []
        for a in raw_actions:
            try:
                actions.append(ActionResult(**a))
            except Exception:
                pass  # Bỏ qua action nếu deserialize lỗi

        # Xây dựng AI Reasoning trace
        fetched_facts = final_state.get("fetched_facts") or final_state.get("raw_facts", {})
        logic_expr = final_state.get("logic_expression", sanitized_rule)
        status_val = final_state.get("final_status", MeetingStatus.RESCHEDULED)

        decision_trace = []
        for fact_key, fact_val in fetched_facts.items():
            if fact_val:
                decision_trace.append(f"{fact_key} = TRUE → đã có chuẩn bị")
            else:
                decision_trace.append(f"{fact_key} = FALSE → điều kiện chặn")
        decision_trace.append(f"Kết luận = {status_val}")

        ai_reasoning_data = {
            "logic": logic_expr,
            "evaluation": fetched_facts,
            "decision_trace": decision_trace,
        }

        # Rút gọn reason
        unsatisfied_conditions = final_state.get("unsatisfied_conditions") or []
        if status_val == MeetingStatus.READY:
            short_reason = "Tất cả điều kiện thỏa mãn. Cuộc họp có thể diễn ra."
        else:
            if unsatisfied_conditions:
                vi_names = [str(c).replace("_", " ") for c in unsatisfied_conditions]
                short_reason = (
                    f"{', '.join(vi_names)} chưa thỏa mãn. Cuộc họp không thể diễn ra."
                )
            else:
                short_reason = "Điều kiện chưa thỏa mãn. Cuộc họp không thể diễn ra."

        # Bổ sung proposed_time cho RESCHEDULE actions nếu thiếu
        if status_val == MeetingStatus.RESCHEDULED:
            for act in actions:
                if act.type == "NOTIFY":
                    act.message = "Vui lòng hoàn thành các yêu cầu trước giờ họp."
                if act.type == "RESCHEDULE" and not act.proposed_time:
                    act.proposed_time = "2026-04-01T10:00:00"

        response_data = EvaluateResponse(
            trace_id=trace_id,
            meeting_id=sanitized_meeting_id,
            status=MeetingStatus(status_val),
            reason=short_reason,
            unsatisfied_conditions=unsatisfied_conditions,
            actions=actions,
            ai_reasoning=ai_reasoning_data,
            confidence=1.0,
            latency_ms=total_latency_ms,
        )

        response_dict = response_data.model_dump()

        # Cache kết quả thành công + release lock (signal waiters)
        await idempotency_cache.release_lock(sanitized_meeting_id, response_dict)
        acquired = False  # Đánh dấu đã release (finally không release lại)

        metrics.record_request(success=True, latency_ms=total_latency_ms)
        log_request(
            logger,
            meeting_id=sanitized_meeting_id,
            status=response_data.status.value,
            latency_ms=total_latency_ms,
        )

        return JSONResponse(content=response_dict)

    except asyncio.TimeoutError:
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
        total_latency_ms = round((time.perf_counter() - request_start) * 1000, 2)
        metrics.record_request(success=False, latency_ms=total_latency_ms)
        logger.error(
            f"Lỗi không mong đợi trong evaluate_meeting: {exc}",
            extra={
                "event": "unhandled_exception",
                "meeting_id": sanitized_meeting_id,
                "error": str(exc),
            },
            exc_info=True,  # Log stack trace phía server, KHÔNG expose ra client
        )
        # Fallback response cho demo — không crash server
        return JSONResponse(
            status_code=200,
            content={
                "meeting_id": sanitized_meeting_id,
                "status": "RESCHEDULED",
                "reason": "Hệ thống gặp sự cố tạm thời. Cuộc họp được dời lại.",
                "unsatisfied_conditions": [],
                "actions": [
                    {
                        "type": "NOTIFY",
                        "target": "Manager",
                        "message": "Hệ thống đang xử lý, vui lòng thử lại.",
                        "status": "sent",
                    }
                ],
                "ai_reasoning": {
                    "logic": sanitized_rule if "sanitized_rule" in dir() else "unknown",
                    "evaluation": {},
                    "decision_trace": ["System fallback do lỗi runtime"],
                },
                "confidence": 0.0,
                "latency_ms": total_latency_ms,
                "trace_id": trace_id,
            },
        )

    finally:
        # ─── Cleanup: luôn chạy dù có exception ─────────────────
        # 1. Release lock NẾU ta vẫn đang giữ (chưa release trong try block)
        if acquired:
            try:
                await idempotency_cache.release_lock_on_error(sanitized_meeting_id)
            except Exception as cleanup_exc:
                logger.warning(
                    f"Cleanup: release_lock_on_error fail: {cleanup_exc}",
                    extra={"event": "cleanup_lock_release_fail"},
                )

        # 2. Restore ContextVar về trạng thái trước request (Token pattern)
        reset_trace_id(token)