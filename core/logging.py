"""
core/logging.py — Structured JSON logger cho production
"""

import logging
import time
from typing import Any, Optional

from pythonjsonlogger import jsonlogger

from core.config import settings
from core.trace import get_trace_id


class MeetWiseJsonFormatter(jsonlogger.JsonFormatter):
    """
    Custom JSON formatter với các fields chuẩn:
    trace_id, event, step, latency_ms, timestamp
    """

    def add_fields(
        self,
        log_record: dict,
        record: logging.LogRecord,
        message_dict: dict,
    ) -> None:
        super().add_fields(log_record, record, message_dict)

        # Luôn inject trace_id từ context
        log_record["trace_id"] = get_trace_id()

        # ISO timestamp
        log_record["timestamp"] = time.strftime(
            "%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()
        )

        # Level name
        log_record["level"] = record.levelname

        # Loại bỏ fields mặc định không cần thiết
        log_record.pop("color_message", None)


def _build_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # Tránh duplicate handlers

    handler = logging.StreamHandler()
    formatter = MeetWiseJsonFormatter(
        fmt="%(trace_id)s %(timestamp)s %(level)s %(name)s %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger.setLevel(log_level)
    logger.propagate = False

    return logger


def get_logger(name: str) -> logging.Logger:
    """Lấy logger với JSON formatter đã cấu hình sẵn."""
    return _build_logger(name)


def log_node_start(logger: logging.Logger, step: str, **extra: Any) -> float:
    """Log bắt đầu node, trả về timestamp bắt đầu."""
    start_time = time.perf_counter()
    logger.info(
        "Node bắt đầu",
        extra={"event": "node_start", "step": step, **extra},
    )
    return start_time


def log_node_end(
    logger: logging.Logger,
    step: str,
    start_time: float,
    success: bool = True,
    **extra: Any,
) -> float:
    """Log kết thúc node và tính latency."""
    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
    event = "node_end" if success else "node_error"
    logger.info(
        "Node hoàn thành" if success else "Node lỗi",
        extra={
            "event": event,
            "step": step,
            "latency_ms": latency_ms,
            **extra,
        },
    )
    return latency_ms


def log_request(
    logger: logging.Logger,
    meeting_id: str,
    status: Optional[str] = None,
    latency_ms: Optional[float] = None,
    **extra: Any,
) -> None:
    """Log request summary."""
    logger.info(
        "Request xử lý xong",
        extra={
            "event": "request_complete",
            "meeting_id": meeting_id,
            "status": status,
            "latency_ms": latency_ms,
            **extra,
        },
    )
