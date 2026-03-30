"""
agent/state.py — Immutable TypedDict State cho LangGraph (v2)

Quy tắc:
- State là immutable: nodes KHÔNG sửa state trực tiếp
- Mỗi node return dict với các fields được update
- LangGraph sẽ merge (shallow) vào state mới
- Không có shared mutable data
"""

from typing import Any, Dict, List, Optional, TypedDict

from solver.parser import ConditionNode
from solver.z3_engine import VerifyResult


class MeetingState(TypedDict, total=False):
    """
    State của LangGraph pipeline cho Meeting Evaluation.

    Mỗi field đều Optional — LangGraph merge incrementally.

    Flow:
        parse_input → fetch_facts → verify_logic → decide_action
    """

    # ── Metadata ──────────────────────────────────
    trace_id: str
    """UUID trace xuyên suốt pipeline."""

    meeting_id: str
    """ID cuộc họp được đánh giá."""

    request_start_time: float
    """time.perf_counter() lúc bắt đầu request."""

    # ── Input ─────────────────────────────────────
    raw_rule: str
    """Rule gốc từ user (đã sanitized, chưa parse)."""

    raw_facts: Optional[Dict[str, bool]]
    """Facts override từ request body (có thể None)."""

    # ── Sau parse_input node ──────────────────────
    parsed_conditions: Optional[List[str]]
    """Danh sách tên điều kiện extracted từ LLM."""

    parsed_ast: Optional[ConditionNode]
    """AST từ recursive parser (sau khi LLM trả về logic string)."""

    logic_expression: Optional[str]
    """Chuỗi logic expression đã chuẩn hóa (e.g., "(Slide_Done or Sheet_Done) and Manager_Free")"""

    parse_source: Optional[str]
    """Nguồn parse: 'llm' | 'fallback' | 'skip_llm' | 'fallback_retry' | 'safe_default'.
    Dùng để observability: biết khi nào LLM fail và fallback được kích hoạt."""

    # ── Sau fetch_facts node ──────────────────────
    fetched_facts: Optional[Dict[str, bool]]
    """Facts thu thập từ tools hoặc override từ request."""

    # ── Sau verify_logic node ─────────────────────
    verify_result: Optional[VerifyResult]
    """Kết quả từ Z3 engine."""

    # ── Sau decide_action node ────────────────────
    final_status: Optional[str]
    """READY hoặc RESCHEDULED."""

    final_reason: Optional[str]
    """Giải thích lý do quyết định."""

    unsatisfied_conditions: Optional[List[str]]
    """Điều kiện chưa thỏa mãn (từ Z3 unsat_core)."""

    executed_actions: Optional[List[Dict[str, Any]]]
    """Danh sách actions đã thực thi (NOTIFY, RESCHEDULE) khi RESCHEDULED.
    Mỗi action là dict serializable từ ActionResult.model_dump()."""

    # ── Error tracking ────────────────────────────
    error_code: Optional[str]
    """Error code nếu có lỗi."""

    error_message: Optional[str]
    """Error message nếu có lỗi."""

    # ── Performance tracking ──────────────────────
    step_latencies: Optional[Dict[str, float]]
    """Latency (ms) của từng node."""
