"""
models/meeting.py — Pydantic Models cho Meeting CRUD

Tách biệt rõ ràng:
  - MeetingCreate: Input để tạo cuộc họp mới
  - MeetingUpdate: Input để cập nhật cuộc họp (tất cả fields optional)
  - MeetingResponse: Output trả về client
  - MeetingListResponse: Danh sách cuộc họp có phân trang
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class MeetingCreate(BaseModel):
    """Input để tạo cuộc họp mới."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Tên cuộc họp",
        examples=["Kickoff Q1 2026"],
    )
    description: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Mô tả cuộc họp",
    )
    scheduled_at: datetime = Field(
        ...,
        description="Thời gian dự kiến diễn ra cuộc họp (ISO 8601)",
        examples=["2026-06-01T09:00:00+07:00"],
    )
    duration_minutes: int = Field(
        default=60,
        ge=5,
        le=480,
        description="Thời lượng cuộc họp (phút), từ 5 đến 480",
    )
    location: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Địa điểm hoặc link họp online",
    )
    meeting_url: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Link Google Meet / Zoom",
    )
    rule: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description=(
            "Điều kiện cần thiết để cuộc họp diễn ra (tiếng Việt hoặc tiếng Anh). "
            "AI sẽ phân tích và đánh giá điều kiện này."
        ),
        examples=[
            "(Slide_Done OR Sheet_Done) AND Manager_Free",
            "Slide cập nhật hoặc Sheet chốt số, bắt buộc Manager rảnh",
        ],
    )
    team_id: Optional[UUID] = Field(
        default=None,
        description="ID nhóm (tùy chọn). Nếu có, thành viên nhóm sẽ thấy cuộc họp này.",
    )


class MeetingUpdate(BaseModel):
    """Input để cập nhật cuộc họp. Tất cả fields đều optional."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    scheduled_at: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(default=None, ge=5, le=480)
    location: Optional[str] = Field(default=None, max_length=500)
    meeting_url: Optional[str] = Field(default=None, max_length=1000)
    rule: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    team_id: Optional[UUID] = None

    @model_validator(mode="after")
    def check_at_least_one_field(self) -> "MeetingUpdate":
        """Đảm bảo ít nhất một field được cung cấp."""
        non_none = {k for k, v in self.model_dump().items() if v is not None}
        if not non_none:
            raise ValueError("Phải cung cấp ít nhất một trường để cập nhật.")
        return self


class MeetingResponse(BaseModel):
    """Response trả về khi lấy thông tin cuộc họp."""

    id: UUID
    owner_id: UUID
    team_id: Optional[UUID]
    title: str
    description: Optional[str]
    scheduled_at: datetime
    duration_minutes: int
    location: Optional[str]
    meeting_url: Optional[str]
    rule: str
    status: str  # pending | evaluating | ready | rescheduled | cancelled
    last_evaluated_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MeetingListResponse(BaseModel):
    """Response cho danh sách cuộc họp với phân trang."""

    items: List[MeetingResponse]
    total: int
    page: int
    page_size: int
    has_next: bool
