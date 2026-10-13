"""Pydantic request/response schemas for the ProxyProof API."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["student", "organiser"] = "student"
    organiser_invite_code: str | None = Field(default=None, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Display name cannot be blank.")
        return value


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower()


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


class DeviceRegisterRequest(BaseModel):
    device_key: str = Field(min_length=8, max_length=128)


class DeviceOut(BaseModel):
    id: int
    device_key: str
    is_active: bool
    registered_at: datetime


class RoomCreate(BaseModel):
    building: str = Field(min_length=1, max_length=80)
    room_code: str = Field(min_length=1, max_length=40)
    display_name: str = Field(min_length=1, max_length=120)

    @field_validator("building", "room_code", "display_name")
    @classmethod
    def strip_nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Room fields cannot be blank.")
        return value


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

    @field_validator("subject_label")
    @classmethod
    def normalize_subject(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Subject label cannot be blank.")
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


class BleTokenOut(BaseModel):
    session_id: str
    session_tag: str
    token: str
    expires_at: datetime
    rotation_seconds: int


class BleAttendanceRequest(BaseModel):
    session_tag: str = Field(min_length=12, max_length=12, pattern=r"^[0-9a-fA-F]{12}$")
    token: str = Field(min_length=16, max_length=16, pattern=r"^[0-9a-fA-F]{16}$")
    rssi: int = Field(ge=-127, le=0)


class AttendanceMarkedResponse(BaseModel):
    status: Literal["present"]
    session_id: str
    room_name: str
    subject_label: str
    marked_at: datetime
    method: str


class AttendanceHistoryItem(BaseModel):
    session_id: str
    room_name: str
    subject_label: str
    scheduled_start_at: datetime
    marked_at: datetime
    method: str
    status: str
    rssi_at_mark: int | None


class AttendanceHistoryResponse(BaseModel):
    items: list[AttendanceHistoryItem]
    eligible_sessions: int
    present_sessions: int
    percentage: float


class ManualAttendanceRequest(BaseModel):
    student_id: int
    status: Literal["present", "absent"]


class AttendanceRosterItem(BaseModel):
    student_id: int
    username: str
    display_name: str
    status: str | None
    marked_at: datetime | None
    method: str | None
    rssi_at_mark: int | None


class AttendanceRosterResponse(BaseModel):
    session_id: str
    room_name: str
    subject_label: str
    scheduled_start_at: datetime
    attendance_deadline: datetime
    attendance_open: bool
    enrolled_count: int
    present_count: int
    records: list[AttendanceRosterItem]
