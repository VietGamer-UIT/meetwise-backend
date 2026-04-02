"""
core/trace.py — Trace ID generation và propagation qua ContextVar
"""

import uuid
from contextvars import ContextVar, Token
from typing import Optional


# ContextVar để propagate trace_id xuyên suốt request lifecycle
_trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)


def generate_trace_id() -> str:
    """Tạo trace ID mới dạng UUID4."""
    return str(uuid.uuid4())


def set_trace_id(trace_id: str) -> Token:
    """Gán trace_id vào context hiện tại. Trả về token để phục hồi."""
    return _trace_id_var.set(trace_id)


def get_trace_id() -> str:
    """
    Lấy trace_id từ context hiện tại.
    Nếu chưa có → tự động generate mới.
    """
    trace_id = _trace_id_var.get()
    if trace_id is None:
        trace_id = generate_trace_id()
        _trace_id_var.set(trace_id)
    return trace_id


def reset_trace_id(token: Token) -> None:
    """Reset trace_id sử dụng context var token (an toàn)."""
    _trace_id_var.reset(token)
