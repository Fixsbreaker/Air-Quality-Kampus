"""Точка входа Telegram-бота.

Запуск: python main.py (или через Docker Compose, профиль `bot`).

Бот работает в режиме long polling — для учебного проекта это проще
вебхуков: не нужен публичный HTTPS-адрес и сертификат.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from api_client import ApiClient
from config import load_config
from digest import check_thresholds, send_morning_digest
from handlers import router

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
)
logger = logging.getLogger("bot")

COMMANDS = [
    BotCommand(command="now", description="Воздух сейчас"),
    BotCommand(command="forecast", description="Прогноз на сутки"),
    BotCommand(command="subscribe", description="Подписаться на уведомления"),
    BotCommand(command="unsubscribe", description="Отключить уведомления"),
    BotCommand(command="help", description="О проекте"),
]


async def main() -> None:
    config = load_config()

    bot = Bot(
        token=config.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    client = ApiClient(config.api_base_url, config.admin_token, config.request_timeout)
    # Обработчикам клиент нужен на каждом апдейте — держим его на объекте бота.
    bot.api_client = client  # type: ignore[attr-defined]

    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    scheduler = AsyncIOScheduler(timezone=config.timezone)
    scheduler.add_job(
        send_morning_digest,
        CronTrigger(hour=config.digest_hour, minute=config.digest_minute),
        args=(bot, client),
        id="morning_digest",
        misfire_grace_time=1800,
    )
    scheduler.add_job(
        check_thresholds,
        CronTrigger(minute=config.alert_check_minute),
        args=(bot, client),
        id="threshold_alerts",
        misfire_grace_time=600,
    )
    scheduler.start()

    await bot.set_my_commands(COMMANDS)
    logger.info("Бот запущен. API: %s", config.api_base_url)

    try:
        await dispatcher.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await client.close()
        await bot.session.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Выход по сигналу")
