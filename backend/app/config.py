"""Конфигурация приложения. Все значения читаются из переменных окружения."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------- Приложение ----------
    app_env: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"
    tz: str = "Asia/Almaty"
    admin_token: str = "change-me-in-production"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Префикс пути, по которому приложение видно снаружи. На сервере проект
    # отдаётся не с корня домена, а по адресу вида esg.kbtu.kz/air-quality,
    # и Swagger должен запрашивать схему с учётом этого префикса. На сами
    # маршруты не влияет: они остаются абсолютными, префикс снимает прокси.
    root_path: str = ""

    # ---------- База данных ----------
    database_url: str = "postgresql+psycopg://aqi:aqi_password@localhost:5432/aqi"

    # ---------- Кэш (нереляционное хранилище) ----------
    redis_url: str = "redis://localhost:6379/0"
    cache_enabled: bool = True
    cache_ttl_seconds: int = Field(default=300, ge=1, le=3600)

    # ---------- Источники данных ----------
    open_meteo_aq_url: str = "https://air-quality-api.open-meteo.com/v1/air-quality"
    open_meteo_weather_url: str = "https://api.open-meteo.com/v1/forecast"
    open_meteo_weather_archive_url: str = "https://archive-api.open-meteo.com/v1/archive"
    airkaz_url: str = "https://airkaz.org/map_data.php"
    airkaz_enabled: bool = False
    http_timeout_seconds: float = 30.0

    # ---------- Планировщик ----------
    ingest_cron_minute: int = 5
    forecast_cron_minute: int = 15
    retrain_cron_hour: int = 3

    # ---------- ML ----------
    model_dir: str = "models"
    forecast_horizon_hours: int = Field(default=48, ge=1, le=168)
    train_history_days: int = Field(default=730, ge=30)
    aqi_breakpoints: Literal["epa_2024", "epa_2012"] = "epa_2024"

    @field_validator("cors_origins")
    @classmethod
    def _strip_origins(cls, value: str) -> str:
        return value.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Кэшированный доступ к настройкам — читаем окружение один раз за процесс."""
    return Settings()


settings = get_settings()
