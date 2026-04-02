"""
schemas/request.py — Pydantic models cho API Request
"""

from typing import Dict, Optional, Any
from pydantic import BaseModel, Field, field_validator, model_validator


class EvaluateRequest(BaseModel):
    """
    Request body cho POST /v1/meetings/evaluate hackathon demo.
    """
    meeting_id: str = Field(..., description="Mã cuộc họp")
    rule: str = Field(..., description="Luật kiểm duyệt ngôn ngữ tự nhiên")
    override_facts: Optional[Dict[str, bool]] = Field(
        default=None, description="Thông tin mock cho các variable"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "meeting_id": "q1-kickoff-2024",
                    "rule": "(Slide_Done OR Sheet_Done) AND Manager_Free",
                    "override_facts": {
                        "Slide_Done": False,
                        "Sheet_Done": True,
                        "Manager_Free": False
                    }
                }
            ]
        }
    }
