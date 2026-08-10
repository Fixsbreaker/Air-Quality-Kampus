"""Рассылки: утренний дайджест и предупреждения о превышении порога.

Отдельно от обработчиков команд, потому что запускается по расписанию,
а не по действию пользователя.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from api_client import ApiClient, ApiError
from texts import format_alert, format_current, format_digest

logger = logging.getLogger(__name__)

# Пауза между сообщениями: Telegram ограничивает массовые рассылки.
SEND_DELAY_SECONDS = 0.05


async def _safe_send(bot: Bot, chat_id: int, text: str) -> bool:
    try:
        await bot.send_message(chat_id, text)
        return True
    except TelegramForbiddenError:
        # Пользователь заблокировал бота — это нормальная ситуация, не ошибка.
        logger.info("Пользователь %s заблокировал бота", chat_id)
        return False
    except TelegramRetryAfter as exc:
        logger.warning("Достигнут лимит Telegram, ждём %s с", exc.retry_after)
        await asyncio.sleep(exc.retry_after)
        return await _safe_send(bot, chat_id, text)
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось отправить сообщение %s", chat_id)
        return False


async def send_morning_digest(bot: Bot, client: ApiClient) -> int:
    """Утренняя сводка всем подписчикам."""
    try:
        subscribers = await client.subscribers()
    except ApiError as exc:
        logger.error("Дайджест не отправлен: %s", exc)
        return 0

    # Данные по локации запрашиваются один раз, а не на каждого подписчика.
    cache: dict[str, tuple[dict, dict | None]] = {}
    sent = 0

    for user in subscribers:
        location = user.get("location", "main")
        if location not in cache:
            try:
                current = await client.current(location)
            except ApiError as exc:
                logger.warning("Нет данных по %s: %s", location, exc)
                continue
            try:
                forecast = await client.forecast(location, hours=24)
            except ApiError:
                forecast = None
            cache[location] = (current, forecast)

        current, forecast = cache[location]
        if await _safe_send(bot, user["tg_id"], format_digest(current, forecast)):
            sent += 1
        await asyncio.sleep(SEND_DELAY_SECONDS)

    logger.info("Утренний дайджест отправлен: %s получателей", sent)
    return sent


async def check_thresholds(bot: Bot, client: ApiClient) -> int:
    """Предупредить тех, у кого текущий AQI выше личного порога."""
    try:
        subscribers = await client.subscribers()
    except ApiError as exc:
        logger.error("Проверка порогов не выполнена: %s", exc)
        return 0

    cache: dict[str, dict] = {}
    sent = 0

    for user in subscribers:
        location = user.get("location", "main")
        if location not in cache:
            try:
                cache[location] = await client.current(location)
            except ApiError as exc:
                logger.warning("Нет данных по %s: %s", location, exc)
                continue

        current = cache[location]
        aqi = current.get("aqi")
        threshold = user.get("threshold_aqi", 100)

        if aqi is None or aqi < threshold:
            continue

        if await _safe_send(bot, user["tg_id"], format_alert(current, threshold)):
            sent += 1
        await asyncio.sleep(SEND_DELAY_SECONDS)

    if sent:
        logger.info("Отправлено предупреждений: %s", sent)
    return sent


async def broadcast_current(bot: Bot, client: ApiClient, chat_ids: list[int]) -> int:
    """Ручная рассылка текущего состояния (используется в отладке)."""
    current = await client.current("main")
    text = format_current(current)
    sent = 0
    for chat_id in chat_ids:
        if await _safe_send(bot, chat_id, text):
            sent += 1
        await asyncio.sleep(SEND_DELAY_SECONDS)
    return sent
