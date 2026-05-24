"""
models/notification.py — Pydantic Models cho Notification System
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    """Response cho một thông báo."""

    id: UUID
    user_id: UUID
    meeting_id: Optional[UUID]
    type: str           # evaluation_complete | meeting_rescheduled | meeting_ready | ...
    title: str
    body: Optional[str]
    action_url: Optional[str]
    is_read: bool
    read_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    """Response danh sách thông báo."""

    items: List[NotificationResponse]
    total: int
    unread_count: int
