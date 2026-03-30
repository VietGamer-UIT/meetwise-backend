"""
schemas/response.py — API Response Models (v4 — Production-Locked)

⚠️  SCHEMA CONTRACT — DO NOT CHANGE
Frontend (Flutter Web) depends on this exact structure.

status: "READY" | "RESCHEDULED"
"""

from typing import Any, Dict, List, Optional
from enum import Enum
from pydantic import BaseModel, Field


class MeetingStatus(str, Enum):
    """Trạng thái kết quả đánh giá cuộc họp."""
    READY        = "READY"         # Đủ điều kiện — cuộc họp diễn ra
    RESCHEDULED  = "RESCHEDULED"   # Thiếu điều kiện — cần dời


# ─────────────────────────────────────────────
# ACTION MODELS
# ─────────────────────────────────────────────

class ActionType(str, Enum):
    NOTIFY     = "NOTIFY"     # Gửi thông báo
    RESCHEDULE = "RESCHEDULE" # Đề xuất lịch mới


class ActionStatus(str, Enum):
    SENT    = "sent"
    FAILED  = "failed"
    SKIPPED = "skipped"


class ActionResult(BaseModel):
    """Kết quả của một action được thực thi."""

    type: ActionType = Field(
        ...,
        description="Loại action: NOTIFY hoặc RESCHEDULE",
    )

    target: Optional[str] = Field(
        default=None,
        description="Đối tượng nhận action (e.g., 'Manager')",
        examples=["Manager"],
    )

    status: ActionStatus = Field(
        ...,
        description="Trạng thái thực thi",
        examples=["sent"],
    )

    message: Optional[str] = Field(
        default=None,
        description="Nội dung message đã gửi (NOTIFY)",
    )

    proposed_time: Optional[str] = Field(
        default=None,
        description="Thời gian đề xuất (ISO 8601, RESCHEDULE)",
        examples=["2026-04-01T10:00:00"],
    )

    error: Optional[str] = Field(
        default=None,
        description="Mô tả lỗi nếu action fail",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "type": "NOTIFY",
                    "target": "Manager",
                    "status": "sent",
                    "message": "Cuộc họp không thể diễn ra do Manager chưa rảnh.",
                },
                {
                    "type": "RESCHEDULE",
                    "target": None,
                    "status": "sent",
                    "proposed_time": "2026-04-01T10:00:00",
                },
            ]
        }
    }


# ─────────────────────────────────────────────
# SUCCESS RESPONSE  ← FRONTEND CONTRACT (LOCKED)
# ─────────────────────────────────────────────

class EvaluateResponse(BaseModel):
    """
    Response trả về khi đánh giá thành công.

    ⚠️  SCHEMA LOCKED — Flutter Web depends on this.
    status: "READY" | "RESCHEDULED"
    """

    trace_id: str = Field(
        ...,
        description="UUID trace để debug",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )

    meeting_id: str = Field(
        ...,
        description="ID cuộc họp được đánh giá",
        examples=["q1-kickoff-2024"],
    )

    status: MeetingStatus = Field(
        ...,
        description="READY = đủ điều kiện | RESCHEDULED = cần dời",
    )

    reason: str = Field(
        ...,
        description="Giải thích lý do quyết định",
        examples=["Điều kiện 'Manager_Free' chưa thỏa mãn."],
    )

    unsatisfied_conditions: List[str] = Field(
        default_factory=list,
        description="Danh sách conditions chưa thỏa mãn (từ Z3 unsat_core)",
        examples=[["Manager_Free"]],
    )

    actions: List[ActionResult] = Field(
        default_factory=list,
        description="Actions đã thực thi khi RESCHEDULED. Rỗng nếu READY.",
    )

    latency_ms: float = Field(
        ...,
        description="Thời gian xử lý (milliseconds)",
        examples=[45.2],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                    "meeting_id": "q1-kickoff-2024",
                    "status": "RESCHEDULED",
                    "reason": "Điều kiện 'Manager_Free' chưa thỏa mãn. Cuộc họp cần được dời.",
                    "unsatisfied_conditions": ["Manager_Free"],
                    "actions": [
                        {
                            "type": "NOTIFY",
                            "target": "Manager",
                            "status": "sent",
                            "message": "Cuộc họp không thể diễn ra do Manager_Free chưa thỏa mãn.",
                        },
                        {
                            "type": "RESCHEDULE",
                            "target": None,
                            "status": "sent",
                            "proposed_time": "2026-04-01T10:00:00",
                        },
                    ],
                    "latency_ms": 45.2,
                }
            ]
        }
    }


# ─────────────────────────────────────────────
# ERROR RESPONSE
# ─────────────────────────────────────────────

class ErrorDetail(BaseModel):
    """Chi tiết lỗi — không expose stack trace."""
    code: str = Field(..., examples=["VALIDATION_ERROR"])
    message: str = Field(..., examples=["meeting_id không hợp lệ"])


class ErrorResponse(BaseModel):
    error: ErrorDetail
    trace_id: str = Field(..., examples=["550e8400-e29b-41d4-a716-446655440000"])

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "rule không được rỗng",
                    },
                    "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                }
            ]
        }
    }


# ─────────────────────────────────────────────
# ERROR CODES
# ─────────────────────────────────────────────

class ErrorCode:
    VALIDATION_ERROR  = "VALIDATION_ERROR"
    BAD_REQUEST       = "BAD_REQUEST"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    LLM_UNAVAILABLE   = "LLM_UNAVAILABLE"
    LLM_PARSE_ERROR   = "LLM_PARSE_ERROR"
    INTERNAL_ERROR    = "INTERNAL_ERROR"
    TIMEOUT           = "TIMEOUT"
    ALREADY_PROCESSING = "ALREADY_PROCESSING"
