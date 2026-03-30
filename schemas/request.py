"""
schemas/request.py — Pydantic models cho API Request
"""

from typing import Dict, Optional, Any
from pydantic import BaseModel, Field, field_validator, model_validator


class EvaluateRequest(BaseModel):
    """
    Request body cho POST /v1/meetings/evaluate

    Validation:
    - meeting_id: không rỗng, tối đa 100 ký tự
    - rule: không rỗng, tối đa 2000 ký tự
    - facts: dict tùy chọn, override facts từ tools
    """

    meeting_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="ID định danh cuộc họp (unique per request)",
        examples=["meeting-2024-q1-kickoff"],
    )

    rule: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Điều kiện họp dạng ngôn ngữ tự nhiên",
        examples=["Chỉ họp nếu Slide cập nhật hoặc Sheet chốt số. Bắt buộc Manager rảnh"],
    )

    facts: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Override facts thay vì fetch từ tools (tùy chọn)",
        examples=[{"Slide_Done": False, "Sheet_Done": True, "Manager_Free": False}],
    )

    @field_validator("meeting_id")
    @classmethod
    def validate_meeting_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("meeting_id không được rỗng sau khi trim")
        # Chỉ cho phép alphanumeric, dash, underscore
        import re
        if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
            raise ValueError(
                "meeting_id chỉ được chứa chữ cái, số, dấu gạch ngang (-) và gạch dưới (_)"
            )
        return v

    @field_validator("rule")
    @classmethod
    def validate_rule(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("rule không được rỗng sau khi trim")
        return v

    @field_validator("facts")
    @classmethod
    def validate_facts(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if v is None:
            return v
        # Validate values phải là bool (hoặc int 0/1)
        sanitized = {}
        for key, val in v.items():
            if not isinstance(key, str):
                raise ValueError(f"Fact key phải là string, nhận được: {type(key)}")
            if isinstance(val, bool):
                sanitized[key] = val
            elif isinstance(val, int) and val in (0, 1):
                sanitized[key] = bool(val)
            else:
                raise ValueError(
                    f"Fact value cho '{key}' phải là boolean (true/false), nhận được: {val}"
                )
        return sanitized

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "meeting_id": "q1-kickoff-2024",
                    "rule": "Chỉ họp nếu Slide cập nhật hoặc Sheet chốt số. Bắt buộc Manager rảnh",
                    "facts": {
                        "Slide_Done": False,
                        "Sheet_Done": True,
                        "Manager_Free": False,
                    },
                }
            ]
        }
    }
