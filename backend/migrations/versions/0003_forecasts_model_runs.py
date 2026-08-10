"""Таблицы ML: forecasts, model_runs

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecasts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("target_ts", sa.DateTime(), nullable=False),
        sa.Column("location", sa.String(length=64), nullable=False),
        sa.Column("horizon_h", sa.Integer(), nullable=False),
        sa.Column("pm25_pred", sa.Float(), nullable=False),
        sa.Column("aqi_pred", sa.Integer(), nullable=False),
        sa.Column("aqi_category", sa.String(length=48), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "target_ts", "location", "model_version", name="uq_forecast_target_loc_model"
        ),
    )
    op.create_index("ix_forecasts_location_target", "forecasts", ["location", "target_ts"])

    op.create_table(
        "model_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("algorithm", sa.String(length=32), nullable=False),
        sa.Column("rows_used", sa.Integer(), nullable=False),
        sa.Column("mae", sa.Float(), nullable=False),
        sa.Column("rmse", sa.Float(), nullable=False),
        sa.Column("baseline_mae", sa.Float(), nullable=False),
        sa.Column("baseline_rmse", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_version", name="uq_model_runs_version"),
    )


def downgrade() -> None:
    op.drop_table("model_runs")
    op.drop_index("ix_forecasts_location_target", table_name="forecasts")
    op.drop_table("forecasts")
