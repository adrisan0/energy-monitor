"""persist Daikin ONECTA climate readings

Revision ID: 0002_daikin_readings
Revises: 0001_initial
Create Date: 2026-11-11 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_daikin_readings"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daikin_readings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("captured_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device_id", sa.String(length=160), nullable=False),
        sa.Column("device_name", sa.String(length=160), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("is_on", sa.Boolean(), nullable=True),
        sa.Column("operating_mode", sa.String(length=64), nullable=True),
        sa.Column("fan_mode", sa.String(length=64), nullable=True),
        sa.Column("room_temperature_c", sa.Numeric(8, 3), nullable=True),
        sa.Column("outdoor_temperature_c", sa.Numeric(8, 3), nullable=True),
        sa.Column("target_temperature_c", sa.Numeric(8, 3), nullable=True),
        sa.Column("heating_today_kwh", sa.Numeric(12, 4), nullable=True),
        sa.Column("cooling_today_kwh", sa.Numeric(12, 4), nullable=True),
        sa.Column("energy_profiles", sa.JSON(), nullable=False),
        sa.Column("in_error_state", sa.Boolean(), nullable=True),
        sa.Column("in_warning_state", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_daikin_readings_captured_at_utc", "daikin_readings", ["captured_at_utc"])
    op.create_index("ix_daikin_readings_device_id", "daikin_readings", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_daikin_readings_device_id", table_name="daikin_readings")
    op.drop_index("ix_daikin_readings_captured_at_utc", table_name="daikin_readings")
    op.drop_table("daikin_readings")
