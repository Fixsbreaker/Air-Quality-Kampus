"""Перевод числа AQI в конкретное действие.

Ключевая ценность проекта — не индекс, а ответ на два вопроса, ради которых
студент открывает дашборд: «можно ли сегодня заниматься спортом на улице?»
и «можно ли открывать окна в аудитории?».
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.services.aqi import category_color, category_of


@dataclass(frozen=True)
class Recommendation:
    aqi: int
    category: str
    color: str
    text: str
    outdoor_sport: bool
    open_windows: bool
    mask_advised: bool
    sensitive_groups_note: str

    def as_dict(self) -> dict:
        return asdict(self)


_RULES: tuple[tuple[int, str, bool, bool, bool, str], ...] = (
    # (верхняя граница AQI, текст, спорт, окна, маска, примечание для чувствительных)
    (
        50,
        "Занятия на улице без ограничений",
        True,
        True,
        False,
        "Ограничений нет",
    ),
    (
        100,
        "Норма; чувствительным людям — сократить нагрузку",
        True,
        True,
        False,
        "Астматикам и аллергикам снизить интенсивность тренировки",
    ),
    (
        150,
        "Физкультуру перенести в зал; астматикам — маска",
        False,
        True,
        True,
        "Чувствительным группам не находиться на улице дольше 30 минут",
    ),
    (
        200,
        "Отменить занятия на улице, закрыть окна, включить рециркуляцию",
        False,
        False,
        True,
        "Чувствительным группам оставаться в помещении",
    ),
)

_EXTREME = (
    "Минимизировать выход на улицу",
    False,
    False,
    True,
    "Выход на улицу только по необходимости, обязательно респиратор",
)


def recommend(aqi: int) -> Recommendation:
    """Рекомендация по значению индекса."""
    for upper, text, sport, windows, mask, note in _RULES:
        if aqi <= upper:
            return Recommendation(
                aqi=aqi,
                category=category_of(aqi),
                color=category_color(aqi),
                text=text,
                outdoor_sport=sport,
                open_windows=windows,
                mask_advised=mask,
                sensitive_groups_note=note,
            )

    text, sport, windows, mask, note = _EXTREME
    return Recommendation(
        aqi=aqi,
        category=category_of(aqi),
        color=category_color(aqi),
        text=text,
        outdoor_sport=sport,
        open_windows=windows,
        mask_advised=mask,
        sensitive_groups_note=note,
    )


def short_summary(aqi: int) -> str:
    """Однострочная сводка для Telegram-бота."""
    rec = recommend(aqi)
    return f"AQI {aqi} — {rec.category}. {rec.text}."
