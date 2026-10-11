"""SQLAlchemy models for ProxyProof."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now_naive() -> datetime:
    """Return UTC as a naive datetime for consistent SQLite storage."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (UniqueConstraint("building", "room_code", name="uq_room_building_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    building: Mapped[str] = mapped_column(String(80), nullable=False)
    room_code: Mapped[str] = mapped_column(String(40), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)

    sessions: Mapped[list["AttendanceSession"]] = relationship(back_populates="room")


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False, index=True)
    subject_label: Mapped[str] = mapped_column(String(120), nullable=False)
    scheduled_start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attendance_deadline: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)

    room: Mapped[Room] = relationship(back_populates="sessions")
