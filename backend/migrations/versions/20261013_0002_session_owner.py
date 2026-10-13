"""Add organiser ownership to attendance sessions.

Revision ID: 20261013_0002
Revises: 20261013_0001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261013_0002"
down_revision: Union[str, None] = "20261013_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("attendance_sessions")}
    if "created_by_user_id" not in columns:
        with op.batch_alter_table("attendance_sessions") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "created_by_user_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id", name="fk_attendance_sessions_created_by_user_id_users"),
                    nullable=True,
                )
            )
    inspector = sa.inspect(op.get_bind())
    indexes = {item["name"] for item in inspector.get_indexes("attendance_sessions")}
    if "ix_attendance_sessions_created_by_user_id" not in indexes:
        op.create_index(
            "ix_attendance_sessions_created_by_user_id",
            "attendance_sessions",
            ["created_by_user_id"],
            unique=False,
        )


def downgrade() -> None:
    # Keep this additive nullable field during rollback; old application code
    # ignores it, and preserving attendance metadata is safer than dropping data.
    pass
