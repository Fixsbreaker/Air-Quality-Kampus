"""GET /api/current — текущий AQI, категория и рекомендация."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cache import build_key, get_cache
from app.db import get_db
from app.deps import location_dep, to_local, utcnow
from app.locations import CampusLocation
from app.models import Measurement
from app.schemas import CurrentOut, LocationOut, RecommendationOut
from app.services.recommendations import recommend

router = APIRouter(prefix="/api", tags=["Качество воздуха"])

STALE_AFTER_HOURS = 3


@router.get(
    "/current",
    response_model=CurrentOut,
    summary="Текущее состояние воздуха",
    description=(
        "Последнее фактическое наблюдение по точке кампуса. "
        "Строки с будущими метками времени (прогноз источника) отбрасываются — "
        "эндпоинт отдаёт только уже наступивший час."
    ),
)
def get_current(
    db: Annotated[Session, Depends(get_db)],
    location: Annotated[CampusLocation, Depends(location_dep)],
) -> CurrentOut:
    now = utcnow()

    # Данные обновляются раз в час, а запрашиваются постоянно — ответ кэшируется.
    # Кэш сбрасывается принудительно после каждого сбора данных, поэтому TTL
    # здесь лишь страховка на случай, если сброс не отработал.
    cache = get_cache()
    cache_key = build_key("current", location.code)
    if (cached := cache.get(cache_key)) is not None:
        return CurrentOut.model_validate(cached)

    row = db.scalars(
        select(Measurement)
        .where(
            Measurement.location == location.code,
            Measurement.source == "open-meteo",
            Measurement.ts <= now,
        )
        .order_by(Measurement.ts.desc())
        .limit(1)
    ).first()

    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=(
                f"Нет данных по локации '{location.code}'. "
                "Запустите сбор данных: python -m scripts.ingest_once"
            ),
        )

    recommendation = None
    if row.aqi is not None:
        recommendation = RecommendationOut(**recommend(row.aqi).as_dict())

    payload = CurrentOut(
        location=LocationOut(
            code=location.code,
            title=location.title,
            lat=location.lat,
            lon=location.lon,
            description=location.description,
            verified=location.verified,
        ),
        ts=row.ts,
        ts_local=to_local(row.ts),
        source=row.source,
        pm25=row.pm25,
        pm10=row.pm10,
        no2=row.no2,
        o3=row.o3,
        aqi=row.aqi,
        aqi_category=row.aqi_category,
        dominant_pollutant=row.dominant_pollutant,
        recommendation=recommendation,
        stale=(now - row.ts) > timedelta(hours=STALE_AFTER_HOURS),
    )

    cache.set(cache_key, payload.model_dump(mode="json"))
    return payload
