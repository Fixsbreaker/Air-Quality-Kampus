"""Конвейер сбора данных: источник → очистка → база.

Две точки входа:
  * ingest_once  — часовой запуск, тянет небольшое окно вокруг «сейчас»;
  * backfill     — глубокая выкачка архива кусками по 90 дней.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.cache import get_cache
from app.ingestion.airkaz import SOURCE_NAME as AIRKAZ_SOURCE
from app.ingestion.airkaz import fetch_nearby
from app.ingestion.cleaning import clean_air_quality
from app.ingestion.openmeteo import AirQualityRecord, OpenMeteoClient
from app.ingestion.repository import upsert_measurements, upsert_weather
from app.locations import CAMPUS_LOCATIONS, CampusLocation

logger = logging.getLogger(__name__)

SOURCE_OPEN_METEO = "open-meteo"
CHUNK_DAYS = 90  # ограничение на длину одного запроса к архиву


@dataclass
class IngestResult:
    location: str
    measurements: dict[str, int] = field(default_factory=dict)
    weather: dict[str, int] = field(default_factory=dict)
    cleaning: dict[str, int] = field(default_factory=dict)
    airkaz_stations: int = 0

    def as_dict(self) -> dict:
        return {
            "location": self.location,
            "measurements": self.measurements,
            "weather": self.weather,
            "cleaning": self.cleaning,
            "airkaz_stations": self.airkaz_stations,
        }


def ingest_location(
    db: Session,
    client: OpenMeteoClient,
    location: CampusLocation,
    *,
    past_days: int = 2,
    forecast_days: int = 2,
) -> IngestResult:
    """Собрать свежие данные по одной точке кампуса."""
    result = IngestResult(location=location.code)

    raw = client.fetch_air_quality(
        location.lat, location.lon, past_days=past_days, forecast_days=forecast_days
    )
    cleaned, report = clean_air_quality(raw)
    result.cleaning = report.as_dict()
    result.measurements = upsert_measurements(
        db, location, SOURCE_OPEN_METEO, cleaned
    ).as_dict()

    weather = client.fetch_weather(
        location.lat, location.lon, past_days=past_days, forecast_days=forecast_days
    )
    result.weather = upsert_weather(db, location, weather).as_dict()

    # Необязательный источник: если сеть недоступна — просто пропускаем.
    readings = fetch_nearby(location.lat, location.lon)
    result.airkaz_stations = len(readings)
    if readings:
        airkaz_records = [
            AirQualityRecord(ts=item.ts, pm25=item.pm25, pm10=item.pm10, no2=None, o3=None)
            for item in readings[:1]  # ближайший датчик к точке кампуса
        ]
        upsert_measurements(db, location, AIRKAZ_SOURCE, airkaz_records)

    logger.info("Сбор данных завершён: %s", result.as_dict())
    return result


def ingest_once(db: Session, *, past_days: int = 2, forecast_days: int = 2) -> list[IngestResult]:
    """Часовой запуск по всем точкам кампуса."""
    with OpenMeteoClient() as client:
        results = [
            ingest_location(
                db, client, location, past_days=past_days, forecast_days=forecast_days
            )
            for location in CAMPUS_LOCATIONS
        ]

    # Пришли новые наблюдения — кэшированные ответы устарели. Без принудительного
    # сброса дашборд показывал бы прошлый час до истечения TTL.
    get_cache().delete_prefix("aqi:current")
    return results


def _date_chunks(start: date, end: date, size_days: int = CHUNK_DAYS):
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=size_days - 1), end)
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def backfill_location(
    db: Session,
    client: OpenMeteoClient,
    location: CampusLocation,
    start: date,
    end: date,
) -> IngestResult:
    """Выкачать исторический архив по точке кампуса кусками по 90 дней."""
    result = IngestResult(location=location.code)
    total_measurements = {"inserted": 0, "updated": 0}
    total_weather = {"inserted": 0, "updated": 0}

    for chunk_start, chunk_end in _date_chunks(start, end):
        logger.info("Архив %s: %s — %s", location.code, chunk_start, chunk_end)

        raw = client.fetch_air_quality(
            location.lat, location.lon, start_date=chunk_start, end_date=chunk_end
        )
        cleaned, _ = clean_air_quality(raw)
        stats = upsert_measurements(db, location, SOURCE_OPEN_METEO, cleaned)
        total_measurements["inserted"] += stats.inserted
        total_measurements["updated"] += stats.updated

        weather = client.fetch_weather_archive(
            location.lat, location.lon, start_date=chunk_start, end_date=chunk_end
        )
        weather_stats = upsert_weather(db, location, weather)
        total_weather["inserted"] += weather_stats.inserted
        total_weather["updated"] += weather_stats.updated

        db.commit()

    result.measurements = total_measurements
    result.weather = total_weather
    return result


def backfill(db: Session, days: int = 730) -> list[IngestResult]:
    """Полный backfill за N дней по всем точкам кампуса."""
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days)

    with OpenMeteoClient() as client:
        return [
            backfill_location(db, client, location, start, end)
            for location in CAMPUS_LOCATIONS
        ]
