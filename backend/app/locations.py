"""Объекты КБТУ, по которым собираются данные о качестве воздуха.

Координаты получены геокодированием официальных адресов через OpenStreetMap
(Nominatim). Общежитие на Тургут Озала подписано в OSM как «Общежитие КБТУ» —
совпадение подтверждено; по Ислама Каримова геокодер дал только уровень улицы,
поэтому точка помечена `verified=False`.

О пространственном разрешении источника. Open-Meteo отдаёт не замеры, а
результат расчётной модели на регулярной сетке. Проверка часовых рядов за
январь показала, что для всех объектов КБТУ ряды **совпадают полностью**,
включая случай, когда точки попадают в разные узлы сетки:

    Толе би 59           -> узел 43.3, 76.9   среднее за январь 34.46
    Тургут Озала 80      -> узел 43.3, 76.9   среднее за январь 34.46
    Ислама Каримова 70   -> узел 43.2, 76.9   среднее за январь 34.46

Все объекты университета расположены в западной части города, и модель
источника не различает их в принципе. Список объектов сохранён, потому что
схема базы, API и интерфейс уже готовы принимать значения из разных
источников: как только появятся наземные датчики, разделение заработает без
переделки кода. Но обучать модель на трёх копиях одного ряда бессмысленно —
дублирующие ряды отсеиваются в `app/ml/features.py::build_dataset`.
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
    verified: bool = False
    """Координаты подтверждены геокодированием до конкретного здания."""


CAMPUS_LOCATIONS: tuple[CampusLocation, ...] = (
    CampusLocation(
        code="main",
        title="Учебный корпус (Толе би 59)",
        lat=43.25573,
        lon=76.94313,
        description="Главное здание университета, улица Толе би, 59",
        verified=True,
    ),
    CampusLocation(
        code="dorm_ozala",
        title="Общежитие (Тургут Озала 80)",
        lat=43.25219,
        lon=76.88085,
        description="Микрорайон Тастак-3, Алмалинский район, 6 этажей",
        verified=True,
    ),
    CampusLocation(
        code="dorm_karimova",
        title="Общежития (Ислама Каримова 70, к1 и к2)",
        lat=43.23704,
        lon=76.88516,
        description="Микрорайон Тастак-3, Алмалинский район, два корпуса по 5 этажей",
        verified=False,
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
