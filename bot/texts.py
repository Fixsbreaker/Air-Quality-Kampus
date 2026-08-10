"""Тексты сообщений бота.

Вынесены отдельно, чтобы формулировки правились без изменения логики
и чтобы позже можно было добавить казахскую и английскую версии.
"""

from __future__ import annotations

from datetime import datetime

EMOJI_BY_CATEGORY = {
    "Хорошо": "🟢",
    "Умеренно": "🟡",
    "Вредно для чувствительных": "🟠",
    "Вредно": "🔴",
    "Очень вредно": "🟣",
}

START = (
    "👋 Привет! Это бот качества воздуха кампуса КБТУ.\n\n"
    "Отвечаю на два вопроса: можно ли сегодня заниматься спортом на улице "
    "и стоит ли открывать окна в аудитории.\n\n"
    "Команды:\n"
    "/now — что с воздухом прямо сейчас\n"
    "/forecast — прогноз на ближайшие сутки\n"
    "/subscribe — утренний дайджест и предупреждения\n"
    "/unsubscribe — отключить уведомления\n"
    "/help — подробнее о проекте"
)

HELP = (
    "ℹ️ <b>Как это работает</b>\n\n"
    "Каждый час сервис забирает данные о концентрации PM2.5 и PM10 по точкам "
    "кампуса, считает индекс AQI по методике US EPA и переводит его в конкретную "
    "рекомендацию.\n\n"
    "Прогноз на 48 часов строит модель градиентного бустинга, обученная на "
    "двухлетнем архиве наблюдений и погоды.\n\n"
    "<b>Шкала AQI</b>\n"
    "🟢 0–50 — хорошо\n"
    "🟡 51–100 — умеренно\n"
    "🟠 101–150 — вредно для чувствительных\n"
    "🔴 151–200 — вредно\n"
    "🟣 200+ — очень вредно\n\n"
    "Команда /subscribe включает утренний дайджест в 07:30 и предупреждение, "
    "когда индекс превышает ваш порог."
)

SERVICE_UNAVAILABLE = (
    "⚠️ Не удалось получить данные: {error}\n"
    "Попробуйте ещё раз через несколько минут."
)


def emoji_for(category: str | None) -> str:
    return EMOJI_BY_CATEGORY.get(category or "", "⚪️")


def _fmt_time(raw: str) -> str:
    try:
        return datetime.fromisoformat(raw).strftime("%d.%m %H:%M")
    except (TypeError, ValueError):
        return raw


def format_current(data: dict) -> str:
    recommendation = data.get("recommendation") or {}
    lines = [
        f"{emoji_for(data.get('aqi_category'))} <b>AQI {data.get('aqi', '—')}"
        f" — {data.get('aqi_category', 'нет данных')}</b>",
        f"📍 {data['location']['title']}",
        f"🕑 {_fmt_time(data.get('ts_local', ''))} (Алматы)",
        "",
        f"PM2.5: <b>{data.get('pm25', '—')}</b> мкг/м³",
        f"PM10:  <b>{data.get('pm10', '—')}</b> мкг/м³",
    ]

    if recommendation:
        lines += [
            "",
            f"💡 {recommendation['text']}",
            "",
            f"{'✅' if recommendation['outdoor_sport'] else '🚫'} спорт на улице",
            f"{'✅' if recommendation['open_windows'] else '🚫'} открывать окна",
        ]
        if recommendation.get("mask_advised"):
            lines.append("😷 рекомендована маска")

    if data.get("stale"):
        lines += ["", "⚠️ Данные обновлялись более трёх часов назад."]

    return "\n".join(lines)


def format_forecast(data: dict, limit_hours: int = 24) -> str:
    points = data.get("points", [])[:limit_hours]
    if not points:
        return "Прогноз пока не рассчитан."

    lines = [
        f"📈 <b>Прогноз на {len(points)} ч</b> — {data.get('location', 'main')}",
        f"<i>модель {data.get('model_version', '—')}</i>",
        "",
    ]

    for point in points:
        if point["horizon_h"] % 3 != 0 and point["horizon_h"] != 1:
            continue
        lines.append(
            f"{emoji_for(point.get('aqi_category'))} {_fmt_time(point['target_ts'])} "
            f"— AQI {point['aqi_pred']} (PM2.5 {point['pm25_pred']:.0f})"
        )

    worst = data.get("worst")
    if worst:
        lines += [
            "",
            f"⚠️ Пик загрязнения: {_fmt_time(worst['target_ts'])}, "
            f"AQI {worst['aqi_pred']} — {worst.get('aqi_category', '')}",
        ]

    return "\n".join(lines)


def format_digest(data: dict, forecast: dict | None) -> str:
    lines = ["☀️ <b>Доброе утро! Воздух на кампусе:</b>", "", format_current(data)]

    if forecast and forecast.get("worst"):
        worst = forecast["worst"]
        lines += [
            "",
            f"📈 Днём ожидается до AQI {worst['aqi_pred']} "
            f"({_fmt_time(worst['target_ts'])}).",
        ]

    return "\n".join(lines)


def format_alert(data: dict, threshold: int) -> str:
    return (
        f"🚨 <b>Превышен ваш порог AQI {threshold}</b>\n\n"
        f"{format_current(data)}"
    )


def format_subscribed(payload: dict) -> str:
    action = "оформлена" if payload.get("created") else "обновлена"
    return (
        f"✅ Подписка {action}.\n"
        f"Локация: <b>{payload['location']}</b>\n"
        f"Порог предупреждения: <b>AQI {payload['threshold_aqi']}</b>\n\n"
        "Утренний дайджест приходит в 07:30. Порог можно изменить командой "
        "/subscribe &lt;значение&gt;, например: /subscribe 80"
    )
