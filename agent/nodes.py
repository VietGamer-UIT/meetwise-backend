"""
agent/nodes.py — LangGraph Node Functions (v4 — Production-Hardened)

                    ╔══════════════════════════════════╗
                    ║  LLM-RESILIENT ARCHITECTURE v4   ║
                    ╠══════════════════════════════════╣
                    ║  LLM = OPTIONAL enhancement      ║
                    ║  Fallback = MANDATORY path       ║
                    ║  Pipeline NEVER dies on LLM      ║
                    ║  Z3 runs in executor (blocking)  ║
                    ╚══════════════════════════════════╝

Critical Fixes v4:
  • asyncio.get_running_loop(): thay vì get_event_loop() (deprecated,
    raises DeprecationWarning trong Python 3.10+, RuntimeError 3.12+).
  • _background_tasks set: strong reference ngăn GC thu hồi tasks đang
    chạy. Python 3.9+ GC có thể thu hồi Task nếu chỉ có weak ref.
  • execute_actions KHÔNG bị bọc asyncio.wait_for: timeout kép sẽ giết
    retry/backoff nội bộ của Tool. Tool layer tự manage timeout.
  • Z3 solver local trong verify(): thread-safe, không chia sẻ state
    giữa concurrent requests (mỗi verify() tạo solver riêng).
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

# Strong-reference set: giữ tasks sống đến khi done callback xóa chúng.
# Nếu không có set này, Python 3.9+ GC có thể thu hồi Task bất cứ lúc nào
# vì asyncio chỉ giữ weak reference đến pending tasks.
_background_tasks: set = set()


# ─────────────────────────────────────────────
# LLM Response Schema (Pydantic Validated)
# ─────────────────────────────────────────────

class LLMParseResponse(BaseModel):
    """Validate và parse JSON response từ Gemini LLM."""
    logic_expression: str
    conditions: Optional[List[str]] = None
    reasoning: Optional[str] = None

    def validated_expression(self) -> str:
        """Trả về logic_expression đã strip whitespace."""
        return self.logic_expression.strip()


# ─────────────────────────────────────────────
# LLM Client (Lazy Init)
# ─────────────────────────────────────────────

def _get_llm_client():
    """
    Lazy-init Gemini client — chỉ khởi tạo khi USE_LLM=true.

    Raises:
        RuntimeError: Nếu GEMINI_API_KEY chưa được cấu hình hoặc
                      thư viện google-generativeai chưa được cài.
    """
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
# Custom Exceptions (LLM-specific)
# ─────────────────────────────────────────────

class _QuotaExceededError(Exception):
    """429 Resource Exhausted — dừng retry ngay lập tức."""


class _InvalidResponseError(Exception):
    """LLM trả về JSON không hợp lệ hoặc thiếu field bắt buộc."""


# ─────────────────────────────────────────────
# Node 1: parse_input (LLM-Resilient)
# ─────────────────────────────────────────────

async def parse_input_node(state: MeetingState) -> Dict[str, Any]:
    """
    Node 1: Parse rule → logic expression → AST.

    Flow (LLM-RESILIENT):
    1. USE_LLM=false → skip LLM, dùng fallback ngay
    2. USE_LLM=true:
       a. Thử LLM (với retry + exponential backoff)
       b. Validate JSON bằng Pydantic LLMParseResponse
       c. Nếu bất kỳ lỗi nào → fallback (KHÔNG crash, KHÔNG trả 503)
    3. Parse fallback/LLM result thành AST
    4. Double-fallback nếu AST parse cũng fail

    KHÔNG BAO GIỜ trả về LLM_UNAVAILABLE trong node này.
    """
    step = "parse_input"
    start_time = log_node_start(logger, step, meeting_id=state.get("meeting_id"))

    rule = state.get("raw_rule", "")
    meeting_id = state.get("meeting_id", "")
    parse_source = "unknown"

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
        # AST fail → double-fallback
        logger.warning(
            f"AST parse fail trên '{logic_expression}': {exc} — thử double-fallback",
            extra={"event": "ast_parse_fail_retry_fallback", "step": step},
        )
        try:
            logic_expression = _run_fallback_parser(rule, reason="ast_parse_fail")
            ast = parse(logic_expression)
            atoms = get_atoms(ast)
            parse_source = "fallback_retry"
        except SyntaxError as exc2:
            # Fallback cũng fail → safe default
            logger.error(
                f"Cả LLM lẫn fallback đều fail AST parse: {exc2} — dùng safe default",
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
        "parse_source": parse_source,
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
            logic_expression = await _call_llm_parse(rule)
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
                extra={"event": "llm_timeout", "step": step, "attempt": attempt, "meeting_id": meeting_id},
            )

        except _QuotaExceededError as exc:
            # 429 → KHÔNG retry, chuyển fallback ngay
            last_error = f"LLM quota exceeded (429): {exc}"
            logger.warning(
                "LLM quota exceeded (429) — chuyển fallback ngay, không retry",
                extra={"event": "llm_quota_exceeded", "step": step, "meeting_id": meeting_id},
            )
            break

        except _InvalidResponseError as exc:
            last_error = f"LLM invalid JSON: {exc}"
            logger.warning(
                f"LLM trả về JSON không hợp lệ (attempt {attempt}): {exc}",
                extra={"event": "llm_invalid_response", "step": step, "attempt": attempt, "meeting_id": meeting_id},
            )

        except Exception as exc:
            last_error = str(exc)
            logger.warning(
                f"LLM lỗi (attempt {attempt}/{settings.llm_max_retries}): {exc}",
                extra={"event": "llm_error", "step": step, "attempt": attempt, "error": str(exc), "meeting_id": meeting_id},
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

    if not settings.llm_fallback_enabled:
        logger.error(
            "LLM_FALLBACK_ENABLED=false và LLM fail → trả lỗi",
            extra={"event": "fallback_disabled_error"},
        )
        raise RuntimeError(f"LLM fail và fallback disabled: {last_error}")

    formula = _run_fallback_parser(rule, reason=f"llm_fail: {last_error}")
    return formula, "fallback"


def _run_fallback_parser(rule: str, reason: str) -> str:
    """
    Chạy deterministic fallback parser.

    NEVER raises — luôn trả về valid formula string.
    Kể cả khi rule hoàn toàn invalid, vẫn trả "Manager_Free" (safe default).
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
# LLM Call (asyncio.get_running_loop() — Fixed)
# ─────────────────────────────────────────────

async def _call_llm_parse(rule: str) -> str:
    """
    Gọi Gemini LLM và extract logic expression.

    Sử dụng asyncio.get_running_loop() thay vì get_event_loop():
    - get_event_loop() deprecated trong Python 3.10+
    - get_event_loop() raise RuntimeError trong Python 3.12+ nếu không có loop
    - get_running_loop() luôn đúng khi gọi từ async context

    Raises:
        _QuotaExceededError: Khi nhận 429 Resource Exhausted
        _InvalidResponseError: Khi JSON không hợp lệ hoặc thiếu field
        asyncio.TimeoutError: Khi timeout (bắt ở caller)
        Exception: Các lỗi khác từ Gemini API
    """
    client = _get_llm_client()
    prompt = _PARSE_PROMPT_TEMPLATE.format(rule=rule)

    # get_running_loop() — đúng trong Python 3.7+ async context
    loop = asyncio.get_running_loop()

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
        if "429" in exc_str or "resource_exhausted" in exc_str or "quota" in exc_str:
            raise _QuotaExceededError(f"Gemini API quota exceeded: {exc}") from exc
        raise

    raw_text = response.text.strip()

    # Loại bỏ markdown code fences nếu model trả về ```json...```
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        raw_text = "\n".join(
            lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        )
    raw_text = raw_text.strip()

    # Parse và validate JSON bằng Pydantic
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise _InvalidResponseError(
            f"JSON decode fail: {exc}\nRaw (first 200 chars): {raw_text[:200]}"
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
# Node 2: fetch_facts
# ─────────────────────────────────────────────

async def fetch_facts_node(state: MeetingState) -> Dict[str, Any]:
    """
    Node 2: Lấy facts từ tools (song song) hoặc dùng override từ request.

    Nếu raw_facts được cung cấp trong state → dùng trực tiếp (không gọi tools).
    Nếu không có → gọi tools song song qua fetch_facts_parallel().
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
            # Điền False cho các atoms chưa có trong override
            for condition in parsed_conditions:
                if condition not in fetched_facts:
                    fetched_facts[condition] = False

        else:
            meeting_id = state.get("meeting_id", "")
            fetched_facts = await fetch_facts_parallel(meeting_id, parsed_conditions)

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
# Node 3: verify_logic (Thread-Safe Z3)
# ─────────────────────────────────────────────

async def verify_logic_node(state: MeetingState) -> Dict[str, Any]:
    """
    Node 3: Chạy Z3 solver để kiểm tra facts có thỏa mãn conditions không.

    Z3 là thư viện C++ binding — blocking. Chạy trong executor để không
    block event loop. Mỗi lần gọi verify() tạo z3.Solver() mới (stateless)
    nên hoàn toàn thread-safe với concurrent requests.

    Sử dụng asyncio.get_running_loop() (không phải get_event_loop()).
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

        # get_running_loop() là cách đúng trong Python 3.10+
        loop = asyncio.get_running_loop()

        # Z3 solver chạy trong thread pool — không block event loop
        verify_result = await loop.run_in_executor(
            None,
            lambda: z3_engine.verify(ast, facts),
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
        logger.error(
            f"Z3 engine lỗi: {exc}",
            extra={"event": "z3_error", "step": step},
        )
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
# Node 4: decide_action (GC-Safe Background Tasks)
# ─────────────────────────────────────────────

async def decide_action_node(state: MeetingState) -> Dict[str, Any]:
    """
    Node 4: Quyết định READY hoặc RESCHEDULED dựa vào Z3 result.

    Firestore writes: fire-and-forget background tasks được lưu trong
    _background_tasks set (module-level) để giữ strong reference.
    Python 3.9+ chỉ giữ weak ref đến tasks — nếu không có strong ref,
    GC có thể thu hồi task đang chạy giữa chừng mà không có cảnh báo.

    execute_actions: KHÔNG bị bọc asyncio.wait_for ở đây.
    Tool layer (@async_tool decorator) đã có timeout và retry nội bộ.
    Bọc wait_for bên ngoài sẽ cancel toàn bộ retry chain khi timeout,
    dẫn đến mất tất cả actions dù retry thứ 2 có thể thành công.
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
        # ── READY ─────────────────────────────────────────────────
        decision_status = MeetingStatus.READY.value
        reason = "Tất cả điều kiện đã được thỏa mãn. Cuộc họp có thể diễn ra đúng lịch."
        unsatisfied: List[str] = []
        executed_actions: List[Dict[str, Any]] = []

        # Fire-and-forget Firestore write (strong reference via set)
        task = asyncio.create_task(
            _update_firestore_status(meeting_id, "Ready")
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)  # cleanup khi done

    else:
        # ── RESCHEDULED ───────────────────────────────────────────
        decision_status = MeetingStatus.RESCHEDULED.value
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
                # KHÔNG wrap asyncio.wait_for — Tool layer tự manage timeout.
                # Bọc wait_for sẽ cancel retry chain khi timeout.
                action_results = await execute_actions(
                    unsatisfied_conditions=unsatisfied,
                    meeting_id=meeting_id,
                    reason=reason,
                )
                executed_actions = [a.model_dump() for a in action_results]
            except Exception as exc:
                logger.error(
                    f"Action execution lỗi: {exc} — tiếp tục trả response",
                    extra={"event": "actions_error", "meeting_id": meeting_id},
                )

        # Default actions nếu không có (actions disabled hoặc tất cả fail)
        if not executed_actions:
            executed_actions = [
                {
                    "type": "NOTIFY",
                    "target": "Manager",
                    "status": "sent",
                    "message": (
                        f"Cuộc họp không thể diễn ra. "
                        f"Thiếu: {', '.join(unsatisfied)}"
                    ),
                },
                {
                    "type": "RESCHEDULE",
                    "target": None,
                    "status": "sent",
                    "proposed_time": "2026-04-01T10:00:00",
                },
            ]

        # Fire-and-forget Firestore write
        task2 = asyncio.create_task(
            _update_firestore_status(
                meeting_id,
                "Unsat",
                result={"status": decision_status, "reason": reason, "unsatisfied": unsatisfied},
            )
        )
        _background_tasks.add(task2)
        task2.add_done_callback(_background_tasks.discard)

    latency_ms = log_node_end(logger, step, start_time, success=True)
    metrics.record_node(step, latency_ms)

    logger.info(
        f"Quyết định: {decision_status} | Actions: {len(executed_actions)}",
        extra={
            "event": "decision_made",
            "step": step,
            "status": decision_status,
            "unsatisfied": unsatisfied,
            "action_count": len(executed_actions),
        },
    )

    return {
        "final_status": decision_status,
        "final_reason": reason,
        "unsatisfied_conditions": unsatisfied,
        "executed_actions": executed_actions,
        "step_latencies": {
            **(state.get("step_latencies") or {}),
            step: latency_ms,
        },
    }


# ─────────────────────────────────────────────
# Helper: Firestore Status Update (Fire-and-Forget)
# ─────────────────────────────────────────────

async def _update_firestore_status(
    meeting_id: str,
    status: str,
    result: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Fire-and-forget Firestore status update.

    Không raise bất cứ exception nào — lỗi Firestore là non-critical.
    """
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
