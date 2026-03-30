"""
services/sanitizer.py — Input sanitization trước khi gửi LLM

Mục tiêu:
- Loại bỏ prompt injection patterns
- Normalize whitespace
- Loại bỏ null bytes và control characters
- Không thay đổi ngữ nghĩa logic của rule
"""

import re
from typing import Optional

from core.logging import get_logger

logger = get_logger(__name__)

# Patterns nguy hiểm cần loại bỏ/neutralize
_INJECTION_PATTERNS = [
    # Prompt injection phổ biến
    r"ignore\s+(previous|all|above)\s+instructions?",
    r"disregard\s+(previous|all|above)\s+instructions?",
    r"forget\s+(previous|all|above)\s+instructions?",
    r"you\s+are\s+now\s+",
    r"act\s+as\s+",
    r"jailbreak",
    r"DAN\s*:",
    r"<\|system\|>",
    r"<\|user\|>",
    r"<\|assistant\|>",
    # Code injection
    r"```",
    r"<script",
    r"javascript:",
    r"data:text",
]

_COMPILED_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS
]

# Control characters (ngoại trừ tab, newline thông thường)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_rule(rule: str) -> str:
    """
    Làm sạch rule string trước khi gửi LLM.

    Thực hiện:
    1. Loại bỏ null bytes và control characters
    2. Chuẩn hóa whitespace
    3. Kiểm tra injection patterns → raise nếu phát hiện
    4. Giới hạn độ dài (đã validate ở schema, nhưng double-check)

    Args:
        rule: Chuỗi rule ngôn ngữ tự nhiên

    Returns:
        Chuỗi đã được làm sạch

    Raises:
        ValueError: Nếu phát hiện injection pattern
    """
    # 1. Loại bỏ control characters
    cleaned = _CONTROL_CHARS_RE.sub("", rule)

    # 2. Normalize whitespace (nhiều space → một space)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # 3. Kiểm tra injection patterns
    for pattern in _COMPILED_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            logger.warning(
                "Phát hiện injection pattern trong rule",
                extra={
                    "event": "injection_detected",
                    "pattern": pattern.pattern,
                    "matched": match.group(0),
                },
            )
            raise ValueError(
                f"Rule chứa nội dung không hợp lệ: '{match.group(0)}'. "
                "Vui lòng chỉ nhập điều kiện họp bình thường."
            )

    # 4. Double-check độ dài
    if len(cleaned) > 2000:
        cleaned = cleaned[:2000]
        logger.warning(
            "Rule bị cắt ngắn do vượt quá 2000 ký tự",
            extra={"event": "rule_truncated"},
        )

    return cleaned


def sanitize_meeting_id(meeting_id: str) -> str:
    """
    Làm sạch meeting_id (đã validate ở schema nhưng extra safety).

    Args:
        meeting_id: ID cuộc họp

    Returns:
        meeting_id đã trim
    """
    return meeting_id.strip()[:100]
