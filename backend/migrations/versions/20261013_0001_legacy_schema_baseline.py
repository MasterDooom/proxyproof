"""Create missing ProxyProof tables while preserving the prototype schema.

Revision ID: 20261013_0001
Revises:
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261013_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _ensure_index(name: str, table: str, columns: list[str], unique: bool = False) -> None:
    existing = {item["name"] for item in _inspector().get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    # The prototype used create_all() on startup. Adopt those existing tables
    # without recreating or deleting data, while creating any missing tables on
    # a fresh PostgreSQL/SQLite database.
    if not _inspector().has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(length=64), nullable=False),
            sa.Column("display_name", sa.String(length=120), nullable=False),
            sa.Column("password_hash", sa.String(length=256), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    if _inspector().has_table("users"):
        _ensure_index("ix_users_id", "users", ["id"])
        _ensure_index("ix_users_username", "users", ["username"], unique=True)

    if not _inspector().has_table("api_tokens"):
        op.create_table(
            "api_tokens",
            sa.Column("token_hash", sa.String(length=64), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    if _inspector().has_table("api_tokens"):
        _ensure_index("ix_api_tokens_user_id", "api_tokens", ["user_id"])
        _ensure_index("ix_api_tokens_expires_at", "api_tokens", ["expires_at"])

    if not _inspector().has_table("devices"):
        op.create_table(
            "devices",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("device_key", sa.String(length=128), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("registered_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("user_id", name="uq_device_one_per_user"),
            sa.UniqueConstraint("device_key", name="uq_device_key"),
        )
    if _inspector().has_table("devices"):
        _ensure_index("ix_devices_user_id", "devices", ["user_id"])

    if not _inspector().has_table("rooms"):
        op.create_table(
            "rooms",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("building", sa.String(length=80), nullable=False),
            sa.Column("room_code", sa.String(length=40), nullable=False),
            sa.Column("display_name", sa.String(length=120), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("building", "room_code", name="uq_room_building_code"),
        )
    if _inspector().has_table("rooms"):
        _ensure_index("ix_rooms_id", "rooms", ["id"])

    if not _inspector().has_table("room_enrollments"):
        op.create_table(
            "room_enrollments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("user_id", "room_id", name="uq_room_enrollment_user_room"),
        )
    if _inspector().has_table("room_enrollments"):
        _ensure_index("ix_room_enrollments_user_id", "room_enrollments", ["user_id"])
        _ensure_index("ix_room_enrollments_room_id", "room_enrollments", ["room_id"])

    if not _inspector().has_table("attendance_sessions"):
        op.create_table(
            "attendance_sessions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id"), nullable=False),
            sa.Column("subject_label", sa.String(length=120), nullable=False),
            sa.Column("scheduled_start_at", sa.DateTime(), nullable=False),
            sa.Column("attendance_deadline", sa.DateTime(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    if _inspector().has_table("attendance_sessions"):
        _ensure_index("ix_attendance_sessions_room_id", "attendance_sessions", ["room_id"])

    if not _inspector().has_table("session_ble_tags"):
        op.create_table(
            "session_ble_tags",
            sa.Column("session_id", sa.String(length=36), sa.ForeignKey("attendance_sessions.id"), primary_key=True),
            sa.Column("tag", sa.String(length=12), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    if _inspector().has_table("session_ble_tags"):
        _ensure_index("ix_session_ble_tags_tag", "session_ble_tags", ["tag"], unique=True)

    if not _inspector().has_table("attendance_records"):
        op.create_table(
            "attendance_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.String(length=36), sa.ForeignKey("attendance_sessions.id"), nullable=False),
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id"), nullable=True),
            sa.Column("marked_at", sa.DateTime(), nullable=False),
            sa.Column("method", sa.String(length=16), nullable=False),
            sa.Column("rssi_at_mark", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.UniqueConstraint("session_id", "student_id", name="uq_attendance_once_per_session"),
        )
    if _inspector().has_table("attendance_records"):
        _ensure_index("ix_attendance_records_session_id", "attendance_records", ["session_id"])
        _ensure_index("ix_attendance_records_student_id", "attendance_records", ["student_id"])


def downgrade() -> None:
    # This revision can adopt tables created before migrations existed. Dropping
    # them would destroy live attendance data; intentionally preserve them.
    pass
