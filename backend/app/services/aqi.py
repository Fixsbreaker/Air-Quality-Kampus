"""Расчёт индекса качества воздуха (AQI) по методике US EPA.

Индекс считается кусочно-линейной интерполяцией внутри «брейкпоинтов»:

    I = (I_hi - I_lo) / (C_hi - C_lo) * (C - C_lo) + I_lo

где C — концентрация загрязнителя, [C_lo; C_hi] — интервал концентраций,
[I_lo; I_hi] — соответствующий интервал значений индекса.

Перед расчётом концентрация усекается (truncate, а не round) до точности,
предусмотренной методикой: PM2.5 — до 0.1 мкг/м³, PM10 — до целого.

Поддерживаются две редакции брейкпоинтов PM2.5:
  * epa_2024 — действующая редакция (порог «хорошо» снижен до 9.0 мкг/м³);
  * epa_2012 — прежняя редакция, встречается в старых источниках и статьях.
Выбор задаётся настройкой AQI_BREAKPOINTS.

Итоговый AQI = максимум из частных индексов по PM2.5 и PM10. NO2 и O3
сохраняются в базе как концентрации, но в индекс не входят: методика EPA
требует для них другие периоды осреднения (1 ч и 8 ч) и единицы (ppb),
а API отдаёт мгновенные значения в мкг/м³.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.config import settings

# (C_lo, C_hi, I_lo, I_hi)
Breakpoint = tuple[float, float, int, int]

PM25_BREAKPOINTS_2024: tuple[Breakpoint, ...] = (
    (0.0, 9.0, 0, 50),
    (9.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 125.4, 151, 200),
    (125.5, 225.4, 201, 300),
    (225.5, 325.4, 301, 500),
)

PM25_BREAKPOINTS_2012: tuple[Breakpoint, ...] = (
    (0.0, 12.0, 0, 50),
    (12.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 150.4, 151, 200),
    (150.5, 250.4, 201, 300),
    (250.5, 350.4, 301, 400),
    (350.5, 500.4, 401, 500),
)

PM10_BREAKPOINTS: tuple[Breakpoint, ...] = (
    (0, 54, 0, 50),
    (55, 154, 51, 100),
    (155, 254, 101, 150),
    (255, 354, 151, 200),
    (355, 424, 201, 300),
    (425, 504, 301, 400),
    (505, 604, 401, 500),
)

AQI_MAX = 500


@dataclass(frozen=True)
class AqiResult:
    aqi: int
    category: str
    dominant_pollutant: str
    pm25_aqi: int | None
    pm10_aqi: int | None


def _pm25_breakpoints() -> tuple[Breakpoint, ...]:
    if settings.aqi_breakpoints == "epa_2012":
        return PM25_BREAKPOINTS_2012
    return PM25_BREAKPOINTS_2024


def truncate(value: float, decimals: int) -> float:
    """Усечение (не округление) до заданного числа знаков, как требует EPA."""
    factor = 10**decimals
    return math.floor(abs(value) * factor) / factor * (1 if value >= 0 else -1)


def _interpolate(concentration: float, breakpoints: tuple[Breakpoint, ...]) -> int:
    for c_lo, c_hi, i_lo, i_hi in breakpoints:
        if c_lo <= concentration <= c_hi:
            index = (i_hi - i_lo) / (c_hi - c_lo) * (concentration - c_lo) + i_lo
            return int(round(index))
    # Концентрация выше верхнего брейкпоинта — шкала EPA обрывается на 500.
    return AQI_MAX


def aqi_from_pm25(value: float | None) -> int | None:
    """Частный индекс по PM2.5. None на входе — None на выходе."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if value < 0:
        return None
    return _interpolate(truncate(float(value), 1), _pm25_breakpoints())


def aqi_from_pm10(value: float | None) -> int | None:
    """Частный индекс по PM10."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if value < 0:
        return None
    return _interpolate(truncate(float(value), 0), PM10_BREAKPOINTS)


def category_of(aqi: int) -> str:
    """Категория качества воздуха по шкале из технического задания."""
    if aqi <= 50:
        return "Хорошо"
    if aqi <= 100:
        return "Умеренно"
    if aqi <= 150:
        return "Вредно для чувствительных"
    if aqi <= 200:
        return "Вредно"
    return "Очень вредно"


def category_color(aqi: int) -> str:
    """Цвет плашки на дашборде и в боте (палитра US EPA)."""
    if aqi <= 50:
        return "#009966"
    if aqi <= 100:
        return "#ffde33"
    if aqi <= 150:
        return "#ff9933"
    if aqi <= 200:
        return "#cc0033"
    return "#7e0023"


def compute_aqi(pm25: float | None, pm10: float | None) -> AqiResult | None:
    """Итоговый AQI как максимум частных индексов.

    Возвращает None, если ни один загрязнитель не измерен — в этом случае
    строка всё равно сохраняется в базу, но без индекса.
    """
    pm25_index = aqi_from_pm25(pm25)
    pm10_index = aqi_from_pm10(pm10)

    candidates = [(idx, name) for idx, name in ((pm25_index, "pm25"), (pm10_index, "pm10")) if idx is not None]
    if not candidates:
        return None

    aqi, dominant = max(candidates, key=lambda pair: pair[0])
    return AqiResult(
        aqi=aqi,
        category=category_of(aqi),
        dominant_pollutant=dominant,
        pm25_aqi=pm25_index,
        pm10_aqi=pm10_index,
    )
