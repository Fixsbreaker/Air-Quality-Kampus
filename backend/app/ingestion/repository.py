"""Запись собранных данных в базу.

Upsert реализован «вручную» (выбрать существующие ключи → разделить на
INSERT и UPDATE), а не через ON CONFLICT, чтобы один и тот же код работал
и на PostgreSQL в проде, и на SQLite в тестах.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.openmeteo import AirQualityRecord, WeatherRecord
from app.locations import CampusLocation
from app.models import Measurement, Weather
from app.services.aqi import compute_aqi

logger = logging.getLogger(__name__)


@dataclass
class UpsertStats:
    inserted: int = 0
    updated: int = 0

    def as_dict(self) -> dict[str, int]:
        return {"inserted": self.inserted, "updated": self.updated}


def _existing_measurements(
    db: Session, location: str, source: str, timestamps: list[datetime]
) -> dict[datetime, Measurement]:
    if not timestamps:
        return {}
    rows = db.scalars(
        select(Measurement).where(
            Measurement.location == location,
            Measurement.source == source,
            Measurement.ts.in_(timestamps),
        )
    ).all()
    return {row.ts: row for row in rows}


def upsert_measurements(
    db: Session,
    location: CampusLocation,
    source: str,
    records: list[AirQualityRecord],
) -> UpsertStats:
    """Сохранить наблюдения, попутно посчитав AQI и категорию."""
    stats = UpsertStats()
    if not records:
        return stats

    existing = _existing_measurements(db, location.code, source, [r.ts for r in records])

    for record in records:
        result = compute_aqi(record.pm25, record.pm10)
        payload = {
            "pm25": record.pm25,
            "pm10": record.pm10,
            "no2": record.no2,
            "o3": record.o3,
            "aqi": result.aqi if result else None,
            "aqi_category": result.category if result else None,
            "dominant_pollutant": result.dominant_pollutant if result else None,
        }

        row = existing.get(record.ts)
        if row is None:
            db.add(
                Measurement(
                    ts=record.ts,
                    source=source,
                    location=location.code,
                    lat=location.lat,
                    lon=location.lon,
                    **payload,
                )
            )
            stats.inserted += 1
        else:
            for key, value in payload.items():
                setattr(row, key, value)
            stats.updated += 1

    db.flush()
    return stats


def upsert_weather(
    db: Session, location: CampusLocation, records: list[WeatherRecord]
) -> UpsertStats:
    """Сохранить метеоданные для той же точки кампуса."""
    stats = UpsertStats()
    if not records:
        return stats

    timestamps = [r.ts for r in records]
    rows = db.scalars(
        select(Weather).where(Weather.location == location.code, Weather.ts.in_(timestamps))
    ).all()
    existing = {row.ts: row for row in rows}

    for record in records:
        payload = {
            "temp": record.temp,
            "wind_speed": record.wind_speed,
            "wind_dir": record.wind_dir,
            "humidity": record.humidity,
            "pressure": record.pressure,
        }
        row = existing.get(record.ts)
        if row is None:
            db.add(Weather(ts=record.ts, location=location.code, **payload))
            stats.inserted += 1
        else:
            for key, value in payload.items():
                setattr(row, key, value)
            stats.updated += 1

    db.flush()
    return stats
