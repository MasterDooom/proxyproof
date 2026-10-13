"""Add optional organiser ownership to rooms.

Revision ID: 20261013_0003
Revises: 20261013_0002
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261013_0003"
down_revision: Union[str, None] = "20261013_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("rooms")}
    if "created_by_user_id" not in columns:
        op.add_column(
            "rooms",
            sa.Column(
                "created_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
        )
    inspector = sa.inspect(op.get_bind())
    indexes = {item["name"] for item in inspector.get_indexes("rooms")}
    if "ix_rooms_created_by_user_id" not in indexes:
        op.create_index(
            "ix_rooms_created_by_user_id",
            "rooms",
            ["created_by_user_id"],
            unique=False,
        )


def downgrade() -> None:
    # Preserve historical room data and its ownership metadata on rollback.
    pass
