"""Обработчики команд Telegram-бота (aiogram 3)."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from api_client import ApiClient, ApiError
from texts import (
    HELP,
    SERVICE_UNAVAILABLE,
    START,
    format_current,
    format_forecast,
    format_subscribed,
)

logger = logging.getLogger(__name__)
router = Router()

DEFAULT_THRESHOLD = 100


def location_keyboard(locations: list[dict], action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=item["title"], callback_data=f"{action}:{item['code']}")]
            for item in locations
        ]
    )


def get_client(message: Message) -> ApiClient:
    """Клиент API кладётся в workflow_data при старте бота."""
    return message.bot.api_client  # type: ignore[attr-defined]


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(START)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP)


@router.message(Command("now"))
async def cmd_now(message: Message, command: CommandObject) -> None:
    client = get_client(message)
    location = (command.args or "main").strip() or "main"
    try:
        data = await client.current(location)
    except ApiError as exc:
        await message.answer(SERVICE_UNAVAILABLE.format(error=exc))
        return

    try:
        locations = await client.locations()
        keyboard = location_keyboard(locations, "now")
    except ApiError:
        keyboard = None

    await message.answer(format_current(data), reply_markup=keyboard)


@router.message(Command("forecast"))
async def cmd_forecast(message: Message, command: CommandObject) -> None:
    client = get_client(message)
    location = (command.args or "main").strip() or "main"
    try:
        data = await client.forecast(location)
    except ApiError as exc:
        await message.answer(SERVICE_UNAVAILABLE.format(error=exc))
        return

    await message.answer(format_forecast(data))


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, command: CommandObject) -> None:
    client = get_client(message)

    threshold = DEFAULT_THRESHOLD
    if command.args:
        try:
            threshold = int(command.args.strip())
        except ValueError:
            await message.answer(
                "Порог должен быть числом от 1 до 500. Пример: <code>/subscribe 80</code>"
            )
            return
        if not 1 <= threshold <= 500:
            await message.answer("Порог должен быть в диапазоне от 1 до 500.")
            return

    try:
        payload = await client.subscribe(message.from_user.id, threshold, "main")
    except ApiError as exc:
        await message.answer(SERVICE_UNAVAILABLE.format(error=exc))
        return

    await message.answer(format_subscribed(payload))


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message) -> None:
    client = get_client(message)
    try:
        await client.unsubscribe(message.from_user.id)
    except ApiError as exc:
        await message.answer(SERVICE_UNAVAILABLE.format(error=exc))
        return

    await message.answer("🔕 Уведомления отключены. Вернуться можно командой /subscribe.")


@router.callback_query(F.data.startswith("now:"))
async def switch_location(callback: CallbackQuery) -> None:
    client: ApiClient = callback.bot.api_client  # type: ignore[attr-defined]
    location = callback.data.split(":", 1)[1]

    try:
        data = await client.current(location)
    except ApiError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    locations = await client.locations()
    await callback.message.edit_text(
        format_current(data), reply_markup=location_keyboard(locations, "now")
    )
    await callback.answer()


@router.message()
async def fallback(message: Message) -> None:
    await message.answer("Не понял команду. Список команд — /help")
