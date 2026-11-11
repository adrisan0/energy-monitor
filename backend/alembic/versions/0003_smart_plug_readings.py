"""store metering smart plug power history

Revision ID: 0003_smart_plug_readings
Revises: 0002_daikin_readings
Create Date: 2026-11-11 00:00:01
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_smart_plug_readings"
down_revision = "0002_daikin_readings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "smart_plug_readings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("device_name", sa.String(length=160), nullable=False),
        sa.Column("captured_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("online", sa.Boolean(), nullable=False),
        sa.Column("is_on", sa.Boolean(), nullable=True),
        sa.Column("power_w", sa.Numeric(14, 3), nullable=True),
        sa.Column("energy_increment_kwh", sa.Numeric(14, 8), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_smart_plug_readings_device_id", "smart_plug_readings", ["device_id"])
    op.create_index("ix_smart_plug_readings_captured_at_utc", "smart_plug_readings", ["captured_at_utc"])


def downgrade() -> None:
    op.drop_index("ix_smart_plug_readings_captured_at_utc", table_name="smart_plug_readings")
    op.drop_index("ix_smart_plug_readings_device_id", table_name="smart_plug_readings")
    op.drop_table("smart_plug_readings")
