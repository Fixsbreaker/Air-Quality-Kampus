"""Выгрузка данных в CSV для администрации кампуса.

Файл отдаётся потоково (генератором), чтобы годовая выгрузка не собиралась
целиком в оперативной памяти процесса.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import to_local
from app.models import Measurement
from app.services.recommendations import recommend

CSV_HEADER = (
    "ts_utc",
    "ts_almaty",
    "location",
    "source",
    "pm25",
    "pm10",
    "no2",
    "o3",
    "aqi",
    "aqi_category",
    "dominant_pollutant",
    "recommendation",
)

CHUNK_SIZE = 1000


def _row_to_values(row: Measurement) -> tuple:
    recommendation = recommend(row.aqi).text if row.aqi is not None else ""
    return (
        row.ts.isoformat(sep=" "),
        to_local(row.ts).isoformat(sep=" "),
        row.location,
        row.source,
        row.pm25,
        row.pm10,
        row.no2,
        row.o3,
        row.aqi,
        row.aqi_category or "",
        row.dominant_pollutant or "",
        recommendation,
    )


def stream_measurements_csv(
    db: Session,
    from_ts: datetime,
    to_ts: datetime,
    location: str | None = None,
) -> Iterator[str]:
    """Построчная генерация CSV-отчёта за период."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")

    def flush() -> str:
        value = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        return value

    writer.writerow(CSV_HEADER)
    yield flush()

    stmt = (
        select(Measurement)
        .where(Measurement.ts >= from_ts, Measurement.ts <= to_ts)
        .order_by(Measurement.ts)
    )
    if location:
        stmt = stmt.where(Measurement.location == location)

    for row in db.scalars(stmt).yield_per(CHUNK_SIZE):
        writer.writerow(_row_to_values(row))
        if buffer.tell() > 64_000:
            yield flush()

    tail = flush()
    if tail:
        yield tail


def report_filename(from_ts: datetime, to_ts: datetime, location: str | None) -> str:
    suffix = location or "all"
    return f"air_quality_{suffix}_{from_ts:%Y%m%d}_{to_ts:%Y%m%d}.csv"
