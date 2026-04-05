"""
schemas/request.py — Pydantic models cho API Request

Schema Versioning:
──────────────────
  v1: facts (deprecated) — đã xóa
  v2: override_facts — tách biệt hoàn toàn khỏi fetched facts để
      hỗ trợ decoupled testing (ghi đè facts mà không cần Google APIs).

Field Semantics:
  meeting_id:     Định danh cuộc họp (alphanumeric + dấu gạch ngang/gạch dưới).
  rule:           Điều kiện họp bằng ngôn ngữ tự nhiên → LLM sẽ parse thành
                  logic expression → Z3 Solver verify.
  override_facts: Nếu được cung cấp, bỏ qua Google APIs và dùng values này
                  trực tiếp. Dùng cho testing, hackathon demo, dry-run.
"""

from typing import Dict, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class EvaluateRequest(BaseModel):
    """
    Request body cho POST /v1/meetings/evaluate.

    Đây là entry point duy nhất của pipeline:
      rule → LLM parse → Z3 verify → action execution → response

    Attributes:
        meeting_id:     Mã cuộc họp (bắt buộc, ≤ 100 ký tự,
                        chỉ chứa chữ cái, số, dấu gạch ngang/dưới).
        rule:           Điều kiện cuộc họp bằng ngôn ngữ tự nhiên.
                        Ví dụ: "Slide cập nhật hoặc Sheet chốt số, bắt buộc Manager rảnh"
        override_facts: Dict tùy chọn để ghi đè giá trị facts thay vì
                        gọi Google APIs. Dùng cho testing và demo mode.
                        Key: tên biến (e.g., "Slide_Done"); Value: bool.
    """

    meeting_id: str = Field(
        ...,
        description="Mã cuộc họp (alphanumeric, dấu gạch ngang/dưới, tối đa 100 ký tự)",
        min_length=1,
        max_length=100,
        pattern=r"^[a-zA-Z0-9_-]+$",
    )
    rule: str = Field(
        ...,
        description=(
            "Quy tắc điều kiện bằng ngôn ngữ tự nhiên (cho LLM parse). "
            "Ví dụ: '(Slide_Done OR Sheet_Done) AND Manager_Free'"
        ),
        min_length=1,
        max_length=2000,
    )
    override_facts: Optional[Dict[str, bool]] = Field(
        default=None,
        description=(
            "Ghi đè giá trị facts (Dict[str, bool]). "
            "Nếu được cung cấp, bỏ qua Google APIs. "
            "Dùng cho decoupled testing và hackathon demo."
        ),
    )

    @field_validator("rule")
    @classmethod
    def validate_rule(cls, v: str) -> str:
        """Từ chối prompt injection và rule rỗng sau khi strip."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("rule không được rỗng hoặc chỉ chứa khoảng trắng")

        # Detect prompt injection patterns
        injection_patterns = [
            "ignore previous",
            "ignore all",
            "disregard",
            "forget your",
            "you are now",
            "act as",
            "pretend",
            "jailbreak",
            "system prompt",
        ]
        lower = stripped.lower()
        for pattern in injection_patterns:
            if pattern in lower:
                raise ValueError(
                    "rule chứa nội dung không hợp lệ (prompt injection detected)"
                )

        return stripped

    @field_validator("override_facts", mode="before")
    @classmethod
    def validate_override_facts_types(cls, v: Optional[Dict]) -> Optional[Dict]:
        """
        Đảm bảo tất cả values trong override_facts là bool thực sự.

        Pydantic v2 mặc định coerce "yes" → True, 1 → True, v.v.
        Validator này từ chối bất kỳ value nào không phải bool Python gốc.

        Args:
            v: Dict[str, Any] từ JSON body, chưa được validate.

        Returns:
            Dict[str, bool] đã validated.

        Raises:
            ValueError: Nếu bất kỳ value nào không phải bool.
        """
        if v is None:
            return v
        if not isinstance(v, dict):
            raise ValueError("override_facts phải là một object JSON (dict)")
        for key, val in v.items():
            # Phải là bool Python THỰC SỰ — không chấp nhận int, str, None
            if not isinstance(val, bool):
                raise ValueError(
                    f"override_facts['{key}'] phải là boolean (true/false), "
                    f"nhận được: {type(val).__name__} ({val!r})"
                )
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "meeting_id": "q1-kickoff-2024",
                    "rule": "(Slide_Done OR Sheet_Done) AND Manager_Free",
                    "override_facts": {
                        "Slide_Done": False,
                        "Sheet_Done": True,
                        "Manager_Free": False,
                    },
                },
                {
                    "meeting_id": "weekly-sync-w15",
                    "rule": "Slide cập nhật hoặc Sheet chốt số, bắt buộc Manager rảnh",
                    "override_facts": None,
                },
            ]
        }
    }
