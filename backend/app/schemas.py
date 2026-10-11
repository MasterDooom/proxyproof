"""Request and response schemas for the ProxyProof API."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RoomCreate(BaseModel):
    building: str = Field(min_length=1, max_length=80)
    room_code: str = Field(min_length=1, max_length=40)
    display_name: str = Field(min_length=1, max_length=120)


class RoomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    building: str
    room_code: str
    display_name: str
    is_active: bool


class SessionCreate(BaseModel):
    room_id: int
    subject_label: str = Field(min_length=1, max_length=120)
    scheduled_start_at: datetime

    @field_validator("scheduled_start_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scheduled_start_at must include a timezone offset, e.g. +05:30")
        return value


class SessionOut(BaseModel):
    id: str
    room_id: int
    room_name: str
    subject_label: str
    scheduled_start_at: datetime
    attendance_deadline: datetime
    status: str
    attendance_open: bool
