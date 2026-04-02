"""
schemas/request.py — Pydantic models cho API Request
"""

from typing import Dict, Optional, Any
from pydantic import BaseModel, Field, field_validator, model_validator


class EvaluateRequest(BaseModel):
    """
    Request body cho POST /v1/meetings/evaluate hackathon demo.
    """
    slide_done: bool
    sheet_done: bool
    manager_free: bool

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "slide_done": False,
                    "sheet_done": True,
                    "manager_free": False,
                }
            ]
        }
    }
