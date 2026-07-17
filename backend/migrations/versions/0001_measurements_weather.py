"""Базовые таблицы: measurements, weather

Revision ID: 0001
Revises:
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "measurements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("location", sa.String(length=64), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("pm25", sa.Float(), nullable=True),
        sa.Column("pm10", sa.Float(), nullable=True),
        sa.Column("no2", sa.Float(), nullable=True),
        sa.Column("o3", sa.Float(), nullable=True),
        sa.Column("aqi", sa.Integer(), nullable=True),
        sa.Column("aqi_category", sa.String(length=48), nullable=True),
        sa.Column("dominant_pollutant", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ts", "source", "location", name="uq_measurement_ts_source_loc"),
    )
    op.create_index("ix_measurements_ts", "measurements", ["ts"])
    op.create_index("ix_measurements_location_ts", "measurements", ["location", "ts"])

    op.create_table(
        "weather",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("location", sa.String(length=64), nullable=False),
        sa.Column("temp", sa.Float(), nullable=True),
        sa.Column("wind_speed", sa.Float(), nullable=True),
        sa.Column("wind_dir", sa.Float(), nullable=True),
        sa.Column("humidity", sa.Float(), nullable=True),
        sa.Column("pressure", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ts", "location", name="uq_weather_ts_loc"),
    )
    op.create_index("ix_weather_location_ts", "weather", ["location", "ts"])


def downgrade() -> None:
    op.drop_index("ix_weather_location_ts", table_name="weather")
    op.drop_table("weather")
    op.drop_index("ix_measurements_location_ts", table_name="measurements")
    op.drop_index("ix_measurements_ts", table_name="measurements")
    op.drop_table("measurements")
