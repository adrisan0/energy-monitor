from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Energy Home Monitor"
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://energy:change-me-local-password@postgres:5432/energy"
    meter_url: str = "http://192.168.1.31/"
    meter_values_path: str = "/services/user/values.xml"
    meter_devices_path: str = "/services/user/devices.xml"
    meter_device_id: str | None = None
    meter_poll_interval_seconds: int = Field(default=60, ge=5)
    meter_request_timeout_seconds: float = Field(default=5.0, gt=0)
    meter_request_attempts: int = Field(default=3, ge=1, le=10)
    timezone: str = "Europe/Madrid"
    simulation_mode: bool = True

    api_write_token: str = "change-me-local-admin-token"
    local_debug_technical: bool = False
    log_level: str = "INFO"

    feature_automations: bool = False
    feature_telegram: bool = False
    feature_smart_devices: bool = False
    telegram_bot_token: str | None = None
    telegram_bot_tokens: str = ""
    telegram_allowed_chat_ids: str = ""
    telegram_poll_interval_seconds: int = Field(default=3, ge=1)
    telegram_alert_cooldown_seconds: int = Field(default=900, ge=1)
    telegram_import_alert_min_w: int = Field(default=200, ge=0)
    telegram_import_alert_hold_seconds: int = Field(default=120, ge=0)
    home_assistant_base_url: str | None = None
    home_assistant_token: str | None = None
    home_assistant_timeout_seconds: int = Field(default=10, ge=1)
    home_assistant_verify_ssl: bool = True

    backup_dir: Path = Path("/backups")
    backup_retention_days: int = Field(default=30, ge=1)
    backup_schedule_seconds: int = Field(default=86400, ge=60)

    postgres_db: str = "energy"
    postgres_user: str = "energy"
    postgres_password: str = "change-me-local-password"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    max_complete_interval_seconds: int = 180
    prolonged_outage_seconds: int = 600


@lru_cache
def get_settings() -> Settings:
    return Settings()
