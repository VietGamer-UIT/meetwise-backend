"""
agent/nodes.py — LangGraph Node Functions (v3 — LLM-Resilient)

                    ╔══════════════════════════════╗
                    ║  LLM-RESILIENT ARCHITECTURE  ║
                    ╠══════════════════════════════╣
                    ║  LLM = OPTIONAL enhancement  ║
                    ║  Fallback = MANDATORY path   ║
                    ║  Pipeline NEVER dies on LLM  ║
                    ╚══════════════════════════════╝

parse_input flow:
    ┌─ USE_LLM=false ──────────────────────────────────────────────┐
    │  → skip LLM entirely → fallback_parse_rule() → AST          │
    └──────────────────────────────────────────────────────────────┘
    ┌─ USE_LLM=true ───────────────────────────────────────────────┐
    │  try:                                                        │
    │    llm_result = call_llm()          # 1 attempt w/ retry    │
    │    validate JSON (Pydantic)                                  │
    │    parse AST                                                 │
    │  except (429 | timeout | invalid JSON | any):               │
    │    LOG warning (not error)                                   │
    │    fallback_parse_rule()            # deterministic         │
    └──────────────────────────────────────────────────────────────┘

NEVER return LLM_UNAVAILABLE (503).
ALWAYS return valid state with parsed_ast.
"""

import asyncio
import json
import re
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ValidationError

from agent.state import MeetingState
from agent.tools import fetch_facts_parallel
from core.config import settings
from core.logging import get_logger, log_node_start, log_node_end
from core.metrics import metrics
from schemas.response import ErrorCode, MeetingStatus
from solver.parser import parse, get_atoms, ConditionNode
from solver.fallback_parser import fallback_parse_rule, fallback_to_logic_expression
from solver.z3_engine import z3_engine

logger = get_logger(__name__)


# ─────────────────────────────────────────────
# LLM Response Validation (Pydantic)
# ─────────────────────────────────────────────

class LLMParseResponse(BaseModel):
    """Validate và parse JSON response từ LLM."""
    logic_expression: str
    conditions: Optional[List[str]] = None
    reasoning: Optional[str] = None

    def validated_expression(self) -> str:
        """Trả về logic_expression đã strip."""
        return self.logic_expression.strip()


# ─────────────────────────────────────────────
# LLM Client
# ─────────────────────────────────────────────

def _get_llm_client():
    """Lazy-init Gemini client — chỉ khởi tạo khi USE_LLM=true."""
    try:
        import google.genai as genai  # noqa: lazy import
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY chưa được cấu hình")
        return genai.Client(api_key=settings.gemini_api_key)
    except ImportError:
        raise RuntimeError("google-generativeai chưa cài: pip install google-generativeai")


# ─────────────────────────────────────────────
# LLM Prompt Template
# ─────────────────────────────────────────────

_PARSE_PROMPT_TEMPLATE = """
Bạn là hệ thống phân tích điều kiện cuộc họp. Nhiệm vụ của bạn là:
1. Đọc mô tả điều kiện bằng ngôn ngữ tự nhiên
2. Trích xuất các điều kiện boolean cụ thể
3. Chuyển đổi thành biểu thức logic chuẩn hóa

INPUT: {rule}

Quy tắc chuyển đổi:
- "Slide cập nhật" / "Slide xong" / "Slide done" → Slide_Done
- "Sheet chốt số" / "Sheet xong" / "Sheet done" → Sheet_Done
- "Manager rảnh" / "Manager free" / "Manager available" → Manager_Free
- "Attendees xác nhận" / "Mọi người confirm" → Attendees_Confirmed
- "hoặc" / "or" → or
- "và" / "and" / "bắt buộc" → and
- "không" / "not" → not

Nếu điều kiện chưa có trong danh sách trên, hãy tạo tên biến theo format: TitleCase_Snake (e.g., Room_Booked)

QUAN TRỌNG - Trả về JSON hợp lệ theo format sau (không có markdown, không có giải thích):
{{
  "logic_expression": "(Slide_Done or Sheet_Done) and Manager_Free",
  "conditions": ["Slide_Done", "Sheet_Done", "Manager_Free"],
  "reasoning": "Giải thích ngắn gọn bằng tiếng Việt"
}}

Chỉ trả về JSON, không có text nào khác.
"""


# ─────────────────────────────────────────────
# Node: parse_input (v3 — LLM-Resilient)
# ─────────────────────────────────────────────

async def parse_input_node(state: MeetingState) -> Dict[str, Any]:
    """
    Node 1: Parse rule → logic expression → AST

    v3 Architecture (LLM-RESILIENT):
    1. Nếu USE_LLM=false → skip LLM, dùng fallback ngay
    2. Nếu USE_LLM=true:
       a. Thử LLM (với retry)
       b. Validate JSON bằng Pydantic
       c. Nếu bất kỳ lỗi nào → fallback (KHÔNG crash)
    3. Parse fallback result thành AST
    4. KHÔNG BAO GIỜ trả về error vì LLM

    Chỉ trả lỗi nếu: fallback parser cũng fail hoàn toàn (rất hiếm)
    """
    step = "parse_input"
    start_time = log_node_start(logger, step, meeting_id=state.get("meeting_id"))

    rule = state.get("raw_rule", "")
    meeting_id = state.get("meeting_id", "")
    parse_source = "unknown"  # "llm" | "fallback" | "skip_llm"

    logic_expression: Optional[str] = None

    # ── Path 1: USE_LLM=false → skip LLM entirely ──
    if not settings.use_llm:
        logger.info(
            "USE_LLM=false: skip LLM, dùng fallback parser",
            extra={"event": "llm_skipped", "step": step, "meeting_id": meeting_id},
        )
        logic_expression = _run_fallback_parser(rule, reason="USE_LLM=false")
        parse_source = "skip_llm"

    # ── Path 2: USE_LLM=true → try LLM, fallback if fail ──
    else:
        logic_expression, parse_source = await _try_llm_with_fallback(
            rule=rule,
            meeting_id=meeting_id,
            step=step,
        )

    # ── Parse logic expression thành AST ──────────────
    try:
        ast = parse(logic_expression)
        atoms = get_atoms(ast)
    except SyntaxError as exc:
        # Logic expression vẫn invalid → thử fallback một lần nữa
        logger.warning(
            f"AST parse fail trên '{logic_expression}': {exc} — thử fallback",
            extra={"event": "ast_parse_fail_retry_fallback", "step": step},
        )
        try:
            logic_expression = _run_fallback_parser(rule, reason="ast_parse_fail")
            ast = parse(logic_expression)
            atoms = get_atoms(ast)
            parse_source = "fallback_retry"
        except SyntaxError as exc2:
            # Fallback cũng fail → dùng safe default "Manager_Free"
            logger.error(
                f"Cả LLM lẫn fallback đều fail ast parse: {exc2} — dùng Manager_Free",
                extra={"event": "both_parsers_fail", "step": step},
            )
            logic_expression = "Manager_Free"
            ast = parse(logic_expression)
            atoms = get_atoms(ast)
            parse_source = "safe_default"

    latency_ms = log_node_end(logger, step, start_time, success=True)
    metrics.record_node(step, latency_ms)

    logger.info(
        f"parse_input done: source={parse_source}, expr='{logic_expression}', atoms={atoms}",
        extra={
            "event": "parse_input_complete",
            "step": step,
            "meeting_id": meeting_id,
            "parse_source": parse_source,
            "logic_expression": logic_expression,
            "atoms": atoms,
        },
    )

    return {
        "logic_expression": logic_expression,
        "parsed_ast": ast,
        "parsed_conditions": atoms,
        "parse_source": parse_source,  # debug info
        "step_latencies": {
            **(state.get("step_latencies") or {}),
            step: latency_ms,
        },
    }


# ─────────────────────────────────────────────
# LLM → Fallback Strategy
# ─────────────────────────────────────────────

async def _try_llm_with_fallback(
    rule: str,
    meeting_id: str,
    step: str,
) -> tuple[str, str]:
    """
    Thử gọi LLM. Nếu bất kỳ lỗi nào → fallback parser.

    Returns:
        (logic_expression, parse_source)
        parse_source: "llm" | "fallback"
    """
    last_error: Optional[str] = None

    for attempt in range(1, settings.llm_max_retries + 1):
        try:
            logic_expression = await asyncio.wait_for(
                _call_llm_parse(rule),
                timeout=settings.step_timeout_seconds,
            )

            logger.info(
                f"LLM parse thành công (attempt {attempt}): '{logic_expression[:80]}'",
                extra={
                    "event": "llm_parse_success",
                    "step": step,
                    "attempt": attempt,
                    "meeting_id": meeting_id,
                    "expression": logic_expression[:80],
                },
            )
            return logic_expression, "llm"

        except asyncio.TimeoutError:
            last_error = f"LLM timeout sau {settings.step_timeout_seconds}s"
            logger.warning(
                f"LLM timeout (attempt {attempt}/{settings.llm_max_retries})",
                extra={
                    "event": "llm_timeout",
                    "step": step,
                    "attempt": attempt,
                    "meeting_id": meeting_id,
                },
            )

        except _QuotaExceededError as exc:
            # 429 Resource Exhausted → KHÔNG retry, chuyển fallback ngay
            last_error = f"LLM quota exceeded (429): {exc}"
            logger.warning(
                "LLM quota exceeded (429) — chuyển fallback ngay, không retry",
                extra={
                    "event": "llm_quota_exceeded",
                    "step": step,
                    "meeting_id": meeting_id,
                },
            )
            break  # Dừng retry ngay

        except _InvalidResponseError as exc:
            last_error = f"LLM invalid JSON: {exc}"
            logger.warning(
                f"LLM trả về JSON không hợp lệ (attempt {attempt}): {exc}",
                extra={
                    "event": "llm_invalid_response",
                    "step": step,
                    "attempt": attempt,
                    "meeting_id": meeting_id,
                },
            )

        except Exception as exc:
            last_error = str(exc)
            logger.warning(
                f"LLM lỗi (attempt {attempt}/{settings.llm_max_retries}): {exc}",
                extra={
                    "event": "llm_error",
                    "step": step,
                    "attempt": attempt,
                    "error": str(exc),
                    "meeting_id": meeting_id,
                },
            )

        if attempt < settings.llm_max_retries:
            await asyncio.sleep(settings.llm_retry_delay_seconds)

    # ── LLM thất bại → FALLBACK ──
    logger.warning(
        f"LLM không khả dụng sau {settings.llm_max_retries} lần thử "
        f"({last_error}) — chuyển sang fallback parser",
        extra={
            "event": "llm_unavailable_using_fallback",
            "step": step,
            "meeting_id": meeting_id,
            "last_error": last_error,
        },
    )

    # LLM_FALLBACK_ENABLED check (default True, không khuyến khích tắt)
    if not settings.llm_fallback_enabled:
        logger.error(
            "LLM_FALLBACK_ENABLED=false và LLM fail → trả lỗi (behavior cũ)",
            extra={"event": "fallback_disabled_error"},
        )
        raise RuntimeError(f"LLM fail và fallback disabled: {last_error}")

    formula = _run_fallback_parser(rule, reason=f"llm_fail: {last_error}")
    return formula, "fallback"


def _run_fallback_parser(rule: str, reason: str) -> str:
    """
    Chạy deterministic fallback parser.
    NEVER raises — luôn trả về valid formula string.
    """
    logger.info(
        f"Fallback parser kích hoạt | reason={reason}",
        extra={"event": "fallback_parser_activated", "reason": reason},
    )

    result = fallback_parse_rule(rule)
    formula = result["logic_formula"]
    mode = result.get("parse_mode", "unknown")
    confidence = result.get("confidence", 0.0)

    logger.info(
        f"Fallback parser result: formula='{formula}', mode={mode}, confidence={confidence}",
        extra={
            "event": "fallback_parse_used",
            "formula": formula,
            "parse_mode": mode,
            "confidence": confidence,
            "vars": list(result.get("variables", {}).keys()),
        },
    )

    return formula


# ─────────────────────────────────────────────
# Custom Exceptions (LLM-specific)
# ─────────────────────────────────────────────

class _QuotaExceededError(Exception):
    """429 Resource Exhausted — stop retrying immediately."""


class _InvalidResponseError(Exception):
    """LLM trả về JSON không hợp lệ hoặc thiếu field."""


# ─────────────────────────────────────────────
# LLM Call (với structured error detection)
# ─────────────────────────────────────────────

async def _call_llm_parse(rule: str) -> str:
    """
    Gọi Gemini LLM và extract logic expression.

    Raises:
        _QuotaExceededError: Khi nhận 429
        _InvalidResponseError: Khi JSON không hợp lệ
        asyncio.TimeoutError: Khi timeout
        Exception: Các lỗi khác
    """
    client = _get_llm_client()
    prompt = _PARSE_PROMPT_TEMPLATE.format(rule=rule)

    loop = asyncio.get_event_loop()

    try:
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
            ),
        )
    except Exception as exc:
        exc_str = str(exc).lower()
        # Detect 429 Resource Exhausted
        if "429" in exc_str or "resource_exhausted" in exc_str or "quota" in exc_str:
            raise _QuotaExceededError(f"Gemini API quota exceeded: {exc}") from exc
        raise

    raw_text = response.text.strip()

    # Loại bỏ markdown code blocks nếu có
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        # Skip first (```json) and last (```)
        raw_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    raw_text = raw_text.strip()

    # Parse và validate JSON bằng Pydantic
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise _InvalidResponseError(
            f"JSON decode fail: {exc}\nRaw (first 200): {raw_text[:200]}"
        ) from exc

    try:
        parsed = LLMParseResponse(**data)
    except (ValidationError, TypeError) as exc:
        raise _InvalidResponseError(
            f"LLM response schema invalid: {exc}\nData: {data}"
        ) from exc

    expression = parsed.validated_expression()
    if not expression:
        raise _InvalidResponseError("logic_expression rỗng sau validate")

    return expression


# ─────────────────────────────────────────────
# Node: fetch_facts
# ─────────────────────────────────────────────

async def fetch_facts_node(state: MeetingState) -> Dict[str, Any]:
    """
    Node 2: Lấy facts từ tools (song song) hoặc dùng override từ request.

    Nếu raw_facts được cung cấp trong state → dùng trực tiếp (không gọi tools).
    Nếu không có → gọi tools song song qua FirestoreClient.
    """
    step = "fetch_facts"
    start_time = log_node_start(logger, step, meeting_id=state.get("meeting_id"))

    if state.get("error_code"):
        return {}

    try:
        raw_facts = state.get("raw_facts")
        parsed_conditions = state.get("parsed_conditions") or []

        if raw_facts is not None:
            logger.info(
                "Dùng override facts từ request",
                extra={"event": "facts_override", "step": step, "facts": raw_facts},
            )
            fetched_facts = dict(raw_facts)
            for condition in parsed_conditions:
                if condition not in fetched_facts:
                    fetched_facts[condition] = False

        else:
            meeting_id = state.get("meeting_id", "")
            fetched_facts = await asyncio.wait_for(
                fetch_facts_parallel(meeting_id, parsed_conditions),
                timeout=settings.step_timeout_seconds,
            )

        latency_ms = log_node_end(logger, step, start_time, success=True)
        metrics.record_node(step, latency_ms)

        logger.info(
            "Facts đã thu thập xong",
            extra={"event": "facts_ready", "step": step, "facts": fetched_facts},
        )

        return {
            "fetched_facts": fetched_facts,
            "step_latencies": {
                **(state.get("step_latencies") or {}),
                step: latency_ms,
            },
        }

    except asyncio.TimeoutError:
        latency_ms = log_node_end(logger, step, start_time, success=False)
        metrics.record_node(step, latency_ms, error=True)
        return {
            "error_code": ErrorCode.TIMEOUT,
            "error_message": f"Fetch facts timeout sau {settings.step_timeout_seconds}s",
            "step_latencies": {**(state.get("step_latencies") or {}), step: latency_ms},
        }

    except Exception as exc:
        latency_ms = log_node_end(logger, step, start_time, success=False)
        metrics.record_node(step, latency_ms, error=True)
        return {
            "error_code": ErrorCode.INTERNAL_ERROR,
            "error_message": f"Lỗi khi fetch facts: {exc}",
            "step_latencies": {**(state.get("step_latencies") or {}), step: latency_ms},
        }


# ─────────────────────────────────────────────
# Node: verify_logic
# ─────────────────────────────────────────────

async def verify_logic_node(state: MeetingState) -> Dict[str, Any]:
    """
    Node 3: Chạy Z3 solver để kiểm tra facts có thỏa mãn conditions không.
    """
    step = "verify_logic"
    start_time = log_node_start(logger, step, meeting_id=state.get("meeting_id"))

    if state.get("error_code"):
        return {}

    try:
        ast = state.get("parsed_ast")
        facts = state.get("fetched_facts") or {}

        if ast is None:
            raise ValueError("parsed_ast là None — parse_input chưa chạy thành công")
        if not facts:
            raise ValueError("fetched_facts rỗng — fetch_facts chưa chạy thành công")

        loop = asyncio.get_event_loop()
        verify_result = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: z3_engine.verify(ast, facts)),
            timeout=settings.step_timeout_seconds,
        )

        latency_ms = log_node_end(logger, step, start_time, success=True)
        metrics.record_node(step, latency_ms)

        logger.info(
            f"Z3 verify xong: satisfied={verify_result.satisfied}",
            extra={
                "event": "z3_verify_complete",
                "step": step,
                "satisfied": verify_result.satisfied,
                "unsatisfied": verify_result.unsatisfied_conditions,
            },
        )

        return {
            "verify_result": verify_result,
            "step_latencies": {**(state.get("step_latencies") or {}), step: latency_ms},
        }

    except RuntimeError as exc:
        latency_ms = log_node_end(logger, step, start_time, success=False)
        metrics.record_node(step, latency_ms, error=True)
        logger.error(f"Z3 engine lỗi: {exc}", extra={"event": "z3_error", "step": step})
        return {
            "error_code": ErrorCode.INTERNAL_ERROR,
            "error_message": "Lỗi hệ thống khi kiểm tra logic điều kiện.",
            "step_latencies": {**(state.get("step_latencies") or {}), step: latency_ms},
        }

    except asyncio.TimeoutError:
        latency_ms = log_node_end(logger, step, start_time, success=False)
        metrics.record_node(step, latency_ms, error=True)
        return {
            "error_code": ErrorCode.TIMEOUT,
            "error_message": "Z3 verification timeout.",
            "step_latencies": {**(state.get("step_latencies") or {}), step: latency_ms},
        }

    except Exception as exc:
        latency_ms = log_node_end(logger, step, start_time, success=False)
        metrics.record_node(step, latency_ms, error=True)
        return {
            "error_code": ErrorCode.INTERNAL_ERROR,
            "error_message": f"Lỗi không mong đợi trong verify_logic: {exc}",
            "step_latencies": {**(state.get("step_latencies") or {}), step: latency_ms},
        }


# ─────────────────────────────────────────────
# Node: decide_action (v2 — with Action Execution)
# ─────────────────────────────────────────────

async def decide_action_node(state: MeetingState) -> Dict[str, Any]:
    """
    Node 4: Quyết định READY hoặc RESCHEDULED dựa vào Z3 result.

    v2: RESCHEDULED → execute_actions() song song
    """
    step = "decide_action"
    start_time = log_node_start(logger, step, meeting_id=state.get("meeting_id"))

    if state.get("error_code"):
        log_node_end(logger, step, start_time, success=False)
        return {}

    verify_result = state.get("verify_result")

    if verify_result is None:
        log_node_end(logger, step, start_time, success=False)
        return {
            "error_code": ErrorCode.INTERNAL_ERROR,
            "error_message": "verify_result là None — verify_logic chưa chạy.",
        }

    meeting_id = state.get("meeting_id", "")

    if verify_result.satisfied:
        status = MeetingStatus.READY.value
        reason = "Tất cả điều kiện đã được thỏa mãn. Cuộc họp có thể diễn ra đúng lịch."
        unsatisfied: List[str] = []
        executed_actions: List[Dict[str, Any]] = []

        asyncio.create_task(_update_firestore_status(meeting_id, "Ready"))

    else:
        status = MeetingStatus.RESCHEDULED.value
        unsatisfied = verify_result.unsatisfied_conditions or []

        if unsatisfied:
            conditions_str = ", ".join(f"'{c}'" for c in unsatisfied)
            reason = (
                f"Điều kiện bắt buộc chưa thỏa mãn: {conditions_str}. "
                f"{verify_result.explanation}"
            )
        else:
            reason = verify_result.explanation or "Điều kiện cuộc họp chưa được đáp ứng."

        executed_actions = []
        if settings.actions_enabled:
            try:
                from services.action_service import execute_actions
                action_results = await asyncio.wait_for(
                    execute_actions(
                        unsatisfied_conditions=unsatisfied,
                        meeting_id=meeting_id,
                        reason=reason,
                    ),
                    timeout=settings.action_timeout_seconds * len(unsatisfied) + 5,
                )
                executed_actions = [a.model_dump() for a in action_results]
            except asyncio.TimeoutError:
                logger.warning(
                    "Action execution timeout — tiếp tục trả response",
                    extra={"event": "actions_timeout", "meeting_id": meeting_id},
                )
            except Exception as exc:
                logger.error(
                    f"Action execution lỗi: {exc} — tiếp tục trả response",
                    extra={"event": "actions_error", "meeting_id": meeting_id},
                )

        asyncio.create_task(_update_firestore_status(
            meeting_id, "Unsat",
            result={"status": status, "reason": reason, "unsatisfied": unsatisfied}
        ))

    latency_ms = log_node_end(logger, step, start_time, success=True)
    metrics.record_node(step, latency_ms)

    logger.info(
        f"Quyết định: {status} | Actions: {len(executed_actions)}",
        extra={
            "event": "decision_made",
            "step": step,
            "status": status,
            "unsatisfied": unsatisfied,
            "action_count": len(executed_actions),
        },
    )

    return {
        "final_status": status,
        "final_reason": reason,
        "unsatisfied_conditions": unsatisfied,
        "executed_actions": executed_actions,
        "step_latencies": {
            **(state.get("step_latencies") or {}),
            step: latency_ms,
        },
    }


# ─────────────────────────────────────────────
# Helper: Firestore Status Update (fire-and-forget)
# ─────────────────────────────────────────────

async def _update_firestore_status(
    meeting_id: str,
    status: str,
    result: Optional[Dict[str, Any]] = None,
) -> None:
    """Fire-and-forget: không raise nếu fail."""
    try:
        from storage.firestore_client import firestore_client, MeetingStateStatus
        fs_status = MeetingStateStatus(status)
        await firestore_client.update_meeting_status(
            meeting_id=meeting_id,
            status=fs_status,
            result=result,
        )
    except Exception as exc:
        logger.warning(
            f"Firestore status update thất bại (non-critical): {exc}",
            extra={
                "event": "firestore_update_error",
                "meeting_id": meeting_id,
                "status": status,
            },
        )
