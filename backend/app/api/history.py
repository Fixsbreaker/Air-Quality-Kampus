"""GET /api/history — временной ряд для графика на дашборде."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import location_dep, utcnow
from app.locations import CampusLocation
from app.models import Measurement
from app.schemas import HistoryOut, HistoryPoint

router = APIRouter(prefix="/api", tags=["Качество воздуха"])

MAX_RANGE_DAYS = 366
DEFAULT_RANGE_HOURS = 72


@router.get(
    "/history",
    response_model=HistoryOut,
    summary="История наблюдений за период",
    description=(
        "Часовой ряд PM2.5, PM10 и AQI. Без параметров возвращает последние "
        f"{DEFAULT_RANGE_HOURS} часов. Максимальная глубина запроса — {MAX_RANGE_DAYS} дней."
    ),
)
def get_history(
    db: Annotated[Session, Depends(get_db)],
    location: Annotated[CampusLocation, Depends(location_dep)],
    from_ts: Annotated[
        datetime | None, Query(alias="from", description="Начало периода, ISO 8601 (UTC)")
    ] = None,
    to_ts: Annotated[
        datetime | None, Query(alias="to", description="Конец периода, ISO 8601 (UTC)")
    ] = None,
) -> HistoryOut:
    now = utcnow()
    to_ts = to_ts or now
    from_ts = from_ts or (to_ts - timedelta(hours=DEFAULT_RANGE_HOURS))

    if from_ts >= to_ts:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Параметр 'from' должен быть раньше 'to'"
        )
    if (to_ts - from_ts) > timedelta(days=MAX_RANGE_DAYS):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Слишком широкий период: максимум {MAX_RANGE_DAYS} дней",
        )

    rows = db.scalars(
        select(Measurement)
        .where(
            Measurement.location == location.code,
            Measurement.source == "open-meteo",
            Measurement.ts >= from_ts,
            Measurement.ts <= to_ts,
        )
        .order_by(Measurement.ts)
    ).all()

    return HistoryOut(
        location=location.code,
        from_ts=from_ts,
        to_ts=to_ts,
        count=len(rows),
        points=[HistoryPoint.model_validate(row) for row in rows],
    )
