"""Таблицы Telegram-бота: users, alerts

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tg_id", sa.BigInteger(), nullable=False),
        sa.Column("threshold_aqi", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("subscribed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("lang", sa.String(length=8), nullable=False, server_default="ru"),
        sa.Column("location", sa.String(length=64), nullable=False, server_default="main"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tg_id", name="uq_users_tg_id"),
    )
    op.create_index("ix_users_tg_id", "users", ["tg_id"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.Column("aqi", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_user_id", "alerts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_alerts_user_id", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_users_tg_id", table_name="users")
    op.drop_table("users")
