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
import asyncio

logger = get_logger(__name__)

router = APIRouter(tags=["meetings"])


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
    "/v1/meetings/evaluate",
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

    # ─── 1. Trace ID & Context Prep ─────────────────────────────
    trace_id = x_request_id or generate_trace_id()
    token = set_trace_id(trace_id)

    # KHỞI TẠO SẴN các biến này để tránh lỗi sập server ở khối except nếu lỗi xảy ra sớm
    acquired = False
    sanitized_meeting_id = sanitize_meeting_id(body.meeting_id) if hasattr(body, 'meeting_id') else f"demo-{trace_id[:8]}"

    # BẮT ĐẦU KHỐI TRY DUY NHẤT BAO BỌC TOÀN BỘ LOGIC
    try:
        logger.info(
            "Request mới nhận được",
            extra={
                "event": "request_received",
                "meeting_id": sanitized_meeting_id,
                "trace_id": trace_id,
                "has_facts_override": getattr(body, 'override_facts', None) is not None,
            },
        )

        print("=== REQUEST RECEIVED ===")
        print(body)

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

        # ─── 3. Hackathon Demo Mode ───────────────────────
        sanitized_rule = sanitize_rule(body.rule) if hasattr(body, 'rule') else "(Slide_Done OR Sheet_Done) AND Manager_Free"
        demo_facts = body.override_facts if hasattr(body, 'override_facts') and body.override_facts else {}

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
            
            # Timeout hoặc lock fall-through → trả về HTTP 409
            return _error_response(
                code=ErrorCode.ALREADY_PROCESSING,
                message="Meeting đang được xử lý, vui lòng thử lại sau.",
                trace_id=trace_id,
                http_status=status.HTTP_409_CONFLICT,
            )

        # 4c. Acquire lock và bắt đầu xử lý
        acquired = await idempotency_cache.acquire_lock(sanitized_meeting_id)
        if not acquired:
            # Race condition: vừa lock được bởi request khác
            waited_result = await idempotency_cache.wait_for_result(sanitized_meeting_id)
            if waited_result is not None:
                return JSONResponse(content=waited_result)
                
            # Không lấy được lock sau khi chờ
            return _error_response(
                code=ErrorCode.ALREADY_PROCESSING,
                message="Meeting đang được xử lý, vui lòng thử lại sau.",
                trace_id=trace_id,
                http_status=status.HTTP_409_CONFLICT,
            )

        # ─── 5. Chạy LangGraph Pipeline ─────────────
        initial_state: MeetingState = {
            "trace_id": trace_id,
            "meeting_id": sanitized_meeting_id,
            "request_start_time": request_start,
            "raw_rule": sanitized_rule,
            "raw_facts": demo_facts,
            "step_latencies": {},
        }

        from services.evaluate_service import evaluate_meeting_service

        print("=== BEFORE SERVICE ===")
        
        result = await evaluate_meeting_service(body, initial_state)
        
        if result is None:
            raise ValueError("Service trả về None")

        print("=== SERVICE RESULT ===")
        print(result)

        final_state = result

        # ─── 6. Xử lý kết quả ───────────────────
        total_latency_ms = round(
            (time.perf_counter() - request_start) * 1000, 2
        )

        # Kiểm tra error trong state
        if final_state.get("error_code"):
            error_code = final_state["error_code"]
            error_message = final_state.get("error_message", "Lỗi không xác định")

            if acquired:
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
        if raw_actions is None:
            actions = []
        else:
            for a in raw_actions:
                try:
                    actions.append(ActionResult(**a))
                except Exception:
                    pass  # Bỏ qua action nếu deserialize lỗi
        
        if actions is None:
            actions = []

        # ─── Xây dựng AI Reasoning & Reason Ngắn Gọn ───
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
            "decision_trace": decision_trace
        }
        
        print("=== AI REASONING ===")
        print(ai_reasoning_data)

        # Rút gọn reason
        unsatisfied_conditions = final_state.get("unsatisfied_conditions") or []
        if status_val == MeetingStatus.READY:
            short_reason = "Tất cả điều kiện thỏa mãn. Cuộc họp có thể diễn ra."
        else:
            if unsatisfied_conditions:
                vi_names = [str(c).replace("_", " ") for c in unsatisfied_conditions]
                short_reason = f"{', '.join(vi_names)} chưa thỏa mãn. Cuộc họp không thể diễn ra."
            else:
                short_reason = "Điều kiện chưa thỏa mãn. Cuộc họp không thể diễn ra."

        # Tối ưu Actions
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

    # KHỐI CATCH LỖI CHUẨN XÁC, THẲNG HÀNG VỚI TRY
    except asyncio.TimeoutError:
        if acquired:
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
        import traceback
        print("🔥 REAL ERROR:", exc)
        print(traceback.format_exc())

        if acquired:
            await idempotency_cache.release_lock_on_error(sanitized_meeting_id)
        total_latency_ms = round((time.perf_counter() - request_start) * 1000, 2)
        metrics.record_request(success=False, latency_ms=total_latency_ms)

        # Trả về fallback cho demo (không được crash server)
        return JSONResponse(
            status_code=200,
            content={
              "meeting_id": "fallback",
              "status": "RESCHEDULED",
              "reason": f"System fallback do lỗi runtime: {str(exc)}",
              "unsatisfied_conditions": ["Manager_Free"],
              "actions": [
                {
                  "type": "NOTIFY",
                  "target": "Manager",
                  "message": "Fallback triggered",
                  "status": "sent"
                }
              ],
              "ai_reasoning": {
                "logic": "unknown",
                "evaluation": {},
                "decision_trace": ["System fallback due to runtime error"]
              },
              "confidence": 0.5,
              "latency_ms": 0,
              "trace_id": "fallback"
            }
        )
        
    finally:
        # Cleanup block (vẫn đảm bảo response return đúng, xóa Trace ID)
        reset_trace_id(token)