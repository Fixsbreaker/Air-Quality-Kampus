"""Настройки Telegram-бота (читаются из переменных окружения)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class BotConfig:
    token: str
    api_base_url: str
    admin_token: str
    digest_hour: int
    digest_minute: int
    alert_check_minute: int
    timezone: str
    default_location: str = "main"
    request_timeout: float = 15.0


def load_config() -> BotConfig:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "Не задан BOT_TOKEN. Получите токен у @BotFather и добавьте его в .env"
        )

    return BotConfig(
        token=token,
        api_base_url=os.getenv("API_BASE_URL", "http://api:8000").rstrip("/"),
        admin_token=os.getenv("ADMIN_TOKEN", ""),
        digest_hour=_int_env("DIGEST_HOUR", 7),
        digest_minute=_int_env("DIGEST_MINUTE", 30),
        alert_check_minute=_int_env("ALERT_CHECK_MINUTE", 20),
        timezone=os.getenv("TZ", "Asia/Almaty"),
    )
