"""Объекты КБТУ, по которым собираются данные о качестве воздуха.

Координаты сняты приблизительно по карте и требуют сверки с официальными
адресами — точность порядка нескольких сотен метров. Список задан кортежем:
он неизменяем и его можно безопасно импортировать откуда угодно.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CampusLocation:
    code: str
    title: str
    lat: float
    lon: float
    description: str = ""


CAMPUS_LOCATIONS: tuple[CampusLocation, ...] = (
    CampusLocation(
        code="main",
        title="Учебный корпус (Толе би 59)",
        lat=43.2364,
        lon=76.9457,
        description="Главное здание университета",
    ),
    CampusLocation(
        code="dorm_ozala",
        title="Общежитие (Тургут Озала)",
        lat=43.2500,
        lon=76.8800,
        description="Студенческий дом, Алмалинский район",
    ),
    CampusLocation(
        code="dorm_karimova",
        title="Общежития (Ислама Каримова)",
        lat=43.2350,
        lon=76.8850,
        description="Студенческие дома, Алмалинский район",
    ),
)

DEFAULT_LOCATION = CAMPUS_LOCATIONS[0]

LOCATIONS_BY_CODE: dict[str, CampusLocation] = {loc.code: loc for loc in CAMPUS_LOCATIONS}


def get_location(code: str | None) -> CampusLocation:
    """Вернуть объект по коду; без кода — учебный корпус."""
    if not code:
        return DEFAULT_LOCATION
    try:
        return LOCATIONS_BY_CODE[code]
    except KeyError as exc:
        known = ", ".join(LOCATIONS_BY_CODE)
        raise ValueError(f"Неизвестная локация '{code}'. Доступные: {known}") from exc
