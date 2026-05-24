"""
models/user.py — Pydantic Models cho User Management
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserProfileUpdate(BaseModel):
    """Input để cập nhật hồ sơ người dùng."""

    full_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    organization: Optional[str] = Field(default=None, max_length=200)
    job_title: Optional[str] = Field(default=None, max_length=100)
    timezone: Optional[str] = Field(default=None, max_length=50)


class UserProfileResponse(BaseModel):
    """Response cho thông tin hồ sơ người dùng."""

    id: UUID
    email: str
    full_name: Optional[str]
    organization: Optional[str]
    job_title: Optional[str]
    avatar_url: Optional[str]
    timezone: str
    language: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserPublicResponse(BaseModel):
    """Thông tin công khai của user (dùng trong danh sách thành viên)."""

    id: UUID
    full_name: Optional[str]
    avatar_url: Optional[str]
    organization: Optional[str]
