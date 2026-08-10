"""Адаптер к казахстанской сети датчиков Airkaz.org — дополнительный источник.

Статус на момент разработки: публичный эндпоинт `/map_data.php` отвечает
404, документированного API у сети нет. Поэтому источник реализован как
необязательный: при любой ошибке модуль возвращает пустой список и пишет
предупреждение в лог, а сбор данных продолжается по Open-Meteo. Включается
флагом AIRKAZ_ENABLED=true, когда/если эндпоинт снова станет доступен.

Такое поведение заложено в ТЗ («Airkaz не отдаёт данные → Open-Meteo как
основной источник, Airkaz — приятный бонус»).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SOURCE_NAME = "airkaz"
DEFAULT_RADIUS_KM = 3.0


@dataclass(frozen=True)
class AirkazReading:
    ts: datetime
    station: str
    lat: float
    lon: float
    pm25: float | None
    pm10: float | None
    distance_km: float


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние между двумя точками на сфере, км."""
    earth_radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return 2 * earth_radius * math.asin(math.sqrt(a))


def _to_float(value: object) -> float | None:
    if value in (None, "", "null", "-"):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def parse_stations(
    payload: list[dict], lat: float, lon: float, radius_km: float = DEFAULT_RADIUS_KM
) -> list[AirkazReading]:
    """Отобрать станции в радиусе от точки кампуса.

    Формат ответа Airkaz исторически менялся, поэтому разбор намеренно
    терпимый: неизвестные и пустые поля просто пропускаются.
    """
    now = datetime.now(UTC).replace(tzinfo=None, minute=0, second=0, microsecond=0)
    readings: list[AirkazReading] = []

    for raw in payload:
        station_lat = _to_float(raw.get("lat"))
        station_lon = _to_float(raw.get("lng") or raw.get("lon"))
        if station_lat is None or station_lon is None:
            continue

        distance = haversine_km(lat, lon, station_lat, station_lon)
        if distance > radius_km:
            continue

        readings.append(
            AirkazReading(
                ts=now,
                station=str(raw.get("name") or raw.get("id") or "unknown"),
                lat=station_lat,
                lon=station_lon,
                pm25=_to_float(raw.get("pm25") or raw.get("pm2_5")),
                pm10=_to_float(raw.get("pm10")),
                distance_km=round(distance, 3),
            )
        )

    readings.sort(key=lambda item: item.distance_km)
    return readings


def fetch_nearby(
    lat: float,
    lon: float,
    radius_km: float = DEFAULT_RADIUS_KM,
    client: httpx.Client | None = None,
) -> list[AirkazReading]:
    """Получить показания ближайших датчиков. Никогда не бросает исключение."""
    if not settings.airkaz_enabled:
        logger.debug("Airkaz отключён настройкой AIRKAZ_ENABLED")
        return []

    own_client = client is None
    http = client or httpx.Client(timeout=settings.http_timeout_seconds)
    try:
        response = http.get(settings.airkaz_url)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            logger.warning("Airkaz вернул неожиданный формат: %s", type(payload).__name__)
            return []
        return parse_stations(payload, lat, lon, radius_km)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Airkaz недоступен (%s) — работаем на Open-Meteo", exc)
        return []
    finally:
        if own_client:
            http.close()
