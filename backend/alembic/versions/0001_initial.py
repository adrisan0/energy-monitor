"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-02 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meter_samples",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timestamp_local", sa.DateTime(timezone=True), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("local_time", sa.Time(), nullable=False),
        sa.Column("solar_w", sa.Numeric(14, 3), nullable=True),
        sa.Column("grid_import_w", sa.Numeric(14, 3), nullable=True),
        sa.Column("grid_export_w", sa.Numeric(14, 3), nullable=True),
        sa.Column("house_consumption_w", sa.Numeric(14, 3), nullable=True),
        sa.Column("solar_self_consumption_w", sa.Numeric(14, 3), nullable=True),
        sa.Column("solar_self_consumption_percent", sa.Numeric(8, 3), nullable=True),
        sa.Column("voltage_v", sa.Numeric(10, 3), nullable=True),
        sa.Column("current_a", sa.Numeric(10, 3), nullable=True),
        sa.Column("frequency_hz", sa.Numeric(10, 3), nullable=True),
        sa.Column("power_factor", sa.Numeric(8, 4), nullable=True),
        sa.Column("pac1", sa.Numeric(14, 3), nullable=True),
        sa.Column("pac2", sa.Numeric(14, 3), nullable=True),
        sa.Column("fpot1", sa.Numeric(8, 4), nullable=True),
        sa.Column("fpot2", sa.Numeric(8, 4), nullable=True),
        sa.Column("pact", sa.Numeric(14, 3), nullable=True),
        sa.Column("raw_variables", sa.JSON(), nullable=False),
        sa.Column("raw_payload_redacted", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("repeated_payload", sa.Boolean(), nullable=False),
        sa.Column("data_quality", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("poll_duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_meter_samples_id"), "meter_samples", ["id"], unique=False)
    op.create_index(op.f("ix_meter_samples_timestamp_utc"), "meter_samples", ["timestamp_utc"], unique=False)
    op.create_index(op.f("ix_meter_samples_timestamp_local"), "meter_samples", ["timestamp_local"], unique=False)
    op.create_index(op.f("ix_meter_samples_local_date"), "meter_samples", ["local_date"], unique=False)
    op.create_index(op.f("ix_meter_samples_payload_hash"), "meter_samples", ["payload_hash"], unique=False)
    op.create_index(op.f("ix_meter_samples_data_quality"), "meter_samples", ["data_quality"], unique=False)

    op.create_table(
        "energy_aggregates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("period", sa.String(length=16), nullable=False),
        sa.Column("period_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_start_local", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end_local", sa.DateTime(timezone=True), nullable=False),
        sa.Column("solar_kwh", sa.Numeric(18, 6), nullable=False),
        sa.Column("grid_import_kwh", sa.Numeric(18, 6), nullable=False),
        sa.Column("grid_export_kwh", sa.Numeric(18, 6), nullable=False),
        sa.Column("house_consumption_kwh", sa.Numeric(18, 6), nullable=False),
        sa.Column("solar_self_consumption_kwh", sa.Numeric(18, 6), nullable=False),
        sa.Column("self_sufficiency_percent", sa.Numeric(8, 3), nullable=True),
        sa.Column("surplus_export_percent", sa.Numeric(8, 3), nullable=True),
        sa.Column("max_power_w", sa.Numeric(14, 3), nullable=True),
        sa.Column("min_power_w", sa.Numeric(14, 3), nullable=True),
        sa.Column("estimated_cost_eur", sa.Numeric(18, 6), nullable=False),
        sa.Column("compensation_eur", sa.Numeric(18, 6), nullable=False),
        sa.Column("fixed_cost_eur", sa.Numeric(18, 6), nullable=False),
        sa.Column("taxes_eur", sa.Numeric(18, 6), nullable=False),
        sa.Column("net_cost_eur", sa.Numeric(18, 6), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("incomplete_intervals", sa.Integer(), nullable=False),
        sa.Column("is_complete", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("period", "period_start_utc", name=op.f("uq_energy_aggregates_period")),
    )
    op.create_index(op.f("ix_energy_aggregates_period"), "energy_aggregates", ["period"], unique=False)
    op.create_index(op.f("ix_energy_aggregates_period_start_utc"), "energy_aggregates", ["period_start_utc"], unique=False)
    op.create_index(op.f("ix_energy_aggregates_period_start_local"), "energy_aggregates", ["period_start_local"], unique=False)

    op.create_table(
        "tariff_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("flat_price_eur_per_kwh", sa.Numeric(10, 6), nullable=False),
        sa.Column("peak_price_eur_per_kwh", sa.Numeric(10, 6), nullable=False),
        sa.Column("shoulder_price_eur_per_kwh", sa.Numeric(10, 6), nullable=False),
        sa.Column("valley_price_eur_per_kwh", sa.Numeric(10, 6), nullable=False),
        sa.Column("surplus_compensation_eur_per_kwh", sa.Numeric(10, 6), nullable=False),
        sa.Column("monthly_fixed_cost_eur", sa.Numeric(10, 2), nullable=False),
        sa.Column("meter_rental_monthly_eur", sa.Numeric(10, 2), nullable=False),
        sa.Column("electricity_tax_percent", sa.Numeric(8, 4), nullable=False),
        sa.Column("vat_percent", sa.Numeric(8, 4), nullable=False),
        sa.Column("billing_start_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "appliance_annotations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("appliance_name", sa.String(length=120), nullable=False),
        sa.Column("home_area", sa.String(length=120), nullable=True),
        sa.Column("appliance_type", sa.String(length=120), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approx_power_w", sa.Numeric(14, 3), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_appliance_annotations_appliance_name"), "appliance_annotations", ["appliance_name"], unique=False)
    op.create_index(op.f("ix_appliance_annotations_home_area"), "appliance_annotations", ["home_area"], unique=False)
    op.create_index(op.f("ix_appliance_annotations_appliance_type"), "appliance_annotations", ["appliance_type"], unique=False)
    op.create_index(op.f("ix_appliance_annotations_starts_at"), "appliance_annotations", ["starts_at"], unique=False)

    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("manufacturer", sa.String(length=80), nullable=True),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("zone", sa.String(length=120), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("measurement_capable", sa.Boolean(), nullable=False),
        sa.Column("max_power_w", sa.Numeric(14, 3), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("control_mode", sa.String(length=32), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_devices_name"), "devices", ["name"], unique=False)
    op.create_index(op.f("ix_devices_type"), "devices", ["type"], unique=False)
    op.create_index(op.f("ix_devices_zone"), "devices", ["zone"], unique=False)

    op.create_table(
        "system_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_system_events_timestamp_utc"), "system_events", ["timestamp_utc"], unique=False)
    op.create_index(op.f("ix_system_events_event_type"), "system_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_system_events_severity"), "system_events", ["severity"], unique=False)

    op.create_table(
        "backup_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=240), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_backup_records_filename"), "backup_records", ["filename"], unique=False)
    op.create_index(op.f("ix_backup_records_status"), "backup_records", ["status"], unique=False)
    op.create_index(op.f("ix_backup_records_created_at"), "backup_records", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_backup_records_created_at"), table_name="backup_records")
    op.drop_index(op.f("ix_backup_records_status"), table_name="backup_records")
    op.drop_index(op.f("ix_backup_records_filename"), table_name="backup_records")
    op.drop_table("backup_records")
    op.drop_index(op.f("ix_system_events_severity"), table_name="system_events")
    op.drop_index(op.f("ix_system_events_event_type"), table_name="system_events")
    op.drop_index(op.f("ix_system_events_timestamp_utc"), table_name="system_events")
    op.drop_table("system_events")
    op.drop_index(op.f("ix_devices_zone"), table_name="devices")
    op.drop_index(op.f("ix_devices_type"), table_name="devices")
    op.drop_index(op.f("ix_devices_name"), table_name="devices")
    op.drop_table("devices")
    op.drop_index(op.f("ix_appliance_annotations_starts_at"), table_name="appliance_annotations")
    op.drop_index(op.f("ix_appliance_annotations_appliance_type"), table_name="appliance_annotations")
    op.drop_index(op.f("ix_appliance_annotations_home_area"), table_name="appliance_annotations")
    op.drop_index(op.f("ix_appliance_annotations_appliance_name"), table_name="appliance_annotations")
    op.drop_table("appliance_annotations")
    op.drop_table("tariff_settings")
    op.drop_index(op.f("ix_energy_aggregates_period_start_local"), table_name="energy_aggregates")
    op.drop_index(op.f("ix_energy_aggregates_period_start_utc"), table_name="energy_aggregates")
    op.drop_index(op.f("ix_energy_aggregates_period"), table_name="energy_aggregates")
    op.drop_table("energy_aggregates")
    op.drop_index(op.f("ix_meter_samples_data_quality"), table_name="meter_samples")
    op.drop_index(op.f("ix_meter_samples_payload_hash"), table_name="meter_samples")
    op.drop_index(op.f("ix_meter_samples_local_date"), table_name="meter_samples")
    op.drop_index(op.f("ix_meter_samples_timestamp_local"), table_name="meter_samples")
    op.drop_index(op.f("ix_meter_samples_timestamp_utc"), table_name="meter_samples")
    op.drop_index(op.f("ix_meter_samples_id"), table_name="meter_samples")
    op.drop_table("meter_samples")
