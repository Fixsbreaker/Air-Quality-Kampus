"""Кэш ответов на Redis — нереляционное хранилище проекта.

Зачем он здесь. Данные о качестве воздуха обновляются раз в час, а запрашивают
их постоянно: дашборд перезапрашивает каждые пять минут, бот дёргает API на
каждую команду и на каждую рассылку. Считать один и тот же ответ из PostgreSQL
сотни раз в час бессмысленно.

Ключевое требование к реализации — **кэш не должен быть точкой отказа**. Если
Redis недоступен, сервис обязан продолжать работать, просто медленнее. Поэтому
все операции обёрнуты в перехват ошибок: сбой кэша пишется в лог и приводит к
обычному обращению к базе, а не к ошибке у пользователя.

Redis выбран как хранилище «ключ — значение» с встроенным временем жизни
записи: TTL здесь делает ровно то, что нужно, без единой строки кода поверх.
"""

from __future__ import annotations

import contextlib
import json
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

try:  # pragma: no cover - зависит от окружения
    import redis

    REDIS_AVAILABLE = True
except ImportError:  # pragma: no cover
    REDIS_AVAILABLE = False
    logger.warning("Пакет redis не установлен — кэш отключён")


class Cache:
    """Обёртка над Redis, безопасная при недоступности сервера."""

    def __init__(self, url: str | None = None, ttl: int | None = None, enabled: bool | None = None):
        self._ttl = ttl if ttl is not None else settings.cache_ttl_seconds
        self._enabled = settings.cache_enabled if enabled is None else enabled
        self._client: Any = None

        if not self._enabled or not REDIS_AVAILABLE:
            return

        try:
            self._client = redis.Redis.from_url(
                url or settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            self._client.ping()
            logger.info("Кэш подключён: %s, TTL %s c", url or settings.redis_url, self._ttl)
        except Exception as exc:  # noqa: BLE001 - любая ошибка означает работу без кэша
            logger.warning("Redis недоступен (%s) — работаем без кэша", exc)
            self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def get(self, key: str) -> Any | None:
        """Прочитать значение. Ошибка кэша не пробрасывается наружу."""
        if self._client is None:
            return None
        try:
            raw = self._client.get(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось прочитать ключ %s: %s", key, exc)
            return None

        if raw is None:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            logger.warning("Повреждённое значение в кэше по ключу %s", key)
            return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Записать значение с временем жизни. Возвращает признак успеха."""
        if self._client is None:
            return False
        try:
            self._client.setex(
                key,
                ttl if ttl is not None else self._ttl,
                json.dumps(value, ensure_ascii=False, default=str),
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось записать ключ %s: %s", key, exc)
            return False

    def delete_prefix(self, prefix: str) -> int:
        """Сбросить все ключи с указанным префиксом.

        Вызывается после записи новых наблюдений: пока в кэше лежит прошлый
        час, дашборд показывал бы устаревшее значение весь TTL.
        """
        if self._client is None:
            return 0
        try:
            removed = 0
            for key in self._client.scan_iter(match=f"{prefix}*", count=200):
                self._client.delete(key)
                removed += 1
            if removed:
                logger.info("Кэш сброшен по префиксу %s: %s ключей", prefix, removed)
            return removed
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось сбросить кэш по префиксу %s: %s", prefix, exc)
            return 0

    def close(self) -> None:
        if self._client is not None:
            # Ошибка при закрытии не должна мешать остановке сервиса.
            with contextlib.suppress(Exception):
                self._client.close()


def build_key(*parts: object) -> str:
    """Собрать ключ кэша из частей: build_key('current', 'main') -> 'aqi:current:main'."""
    return "aqi:" + ":".join(str(part) for part in parts)


_cache: Cache | None = None


def get_cache() -> Cache:
    """Единственный экземпляр кэша на процесс."""
    global _cache
    if _cache is None:
        _cache = Cache()
    return _cache
