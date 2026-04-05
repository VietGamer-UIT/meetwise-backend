"""
core/trace.py — Trace ID generation và propagation qua ContextVar

Kiến trúc Token-based (Thread-safe & Async-safe):
──────────────────────────────────────────────────
  token = set_trace_id(trace_id)   # Lưu token trả về
  try:
      ...                          # Xử lý business logic
  finally:
      reset_trace_id(token)        # Restore context cha chính xác

Tại sao quan trọng:
  ContextVar.set(value) mà không reset() sẽ mutate context của
  coroutine cha, gây rò rỉ trace_id giữa các request khác nhau
  khi chạy trong cùng một asyncio event loop. Token-based reset
  đảm bảo việc phục hồi luôn đúng về trạng thái trước đó.
"""

import uuid
from contextvars import ContextVar, Token
from typing import Optional


# ContextVar để propagate trace_id xuyên suốt request lifecycle.
# Mỗi asyncio Task kế thừa bản sao riêng của context (copy-on-write),
# do đó safe với concurrent requests.
_trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)


def generate_trace_id() -> str:
    """Tạo trace ID mới dạng UUID4 (globally unique)."""
    return str(uuid.uuid4())


def set_trace_id(trace_id: str) -> Token:
    """
    Gán trace_id vào context hiện tại.

    LUÔN lưu và sử dụng Token trả về để reset sau khi xong việc.
    Không bao giờ dùng _trace_id_var.set(None) để "xóa" — đó là
    anti-pattern gây rò rỉ context sang coroutine cha.

    Args:
        trace_id: Chuỗi trace ID (thường là UUID4 hoặc X-Request-ID).

    Returns:
        Token: Dùng để restore context về trạng thái trước khi set.

    Example::

        token = set_trace_id("req-abc-123")
        try:
            await handle_request()
        finally:
            reset_trace_id(token)
    """
    return _trace_id_var.set(trace_id)


def get_trace_id() -> str:
    """
    Lấy trace_id từ context hiện tại.

    Nếu chưa được set → tự động generate UUID4 mới và gán vào context.
    Hành vi này đảm bảo luôn có trace_id hợp lệ kể cả trong
    background tasks không qua middleware.

    Returns:
        str: Trace ID hợp lệ (không bao giờ None).
    """
    trace_id = _trace_id_var.get()
    if trace_id is None:
        trace_id = generate_trace_id()
        # Không cần lưu token ở đây vì đây là auto-generation;
        # middleware sẽ quản lý lifecycle của token đã set bởi nó.
        _trace_id_var.set(trace_id)
    return trace_id


def reset_trace_id(token: Token) -> None:
    """
    Restore ContextVar về trạng thái trước khi set_trace_id().

    Đây là cách duy nhất an toàn để "xóa" trace_id: không set None
    mà phục hồi chính xác giá trị trước đó (có thể là None hoặc
    trace_id của request cha trong nested calls).

    Args:
        token: Token nhận được từ lần gọi set_trace_id() tương ứng.

    Example::

        token = set_trace_id(trace_id)
        try:
            ...
        finally:
            reset_trace_id(token)   # Luôn chạy dù có exception
    """
    _trace_id_var.reset(token)
