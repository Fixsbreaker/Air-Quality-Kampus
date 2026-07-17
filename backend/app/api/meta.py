"""Справочные эндпоинты: список локаций и проверка здоровья сервиса."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import __version__
from app.db import get_db
from app.locations import CAMPUS_LOCATIONS
from app.ml import registry
from app.models import Measurement
from app.schemas import HealthOut, LocationOut

router = APIRouter(tags=["Служебное"])


@router.get(
    "/api/locations",
    response_model=list[LocationOut],
    summary="Точки кампуса",
    description="Список локаций с координатами — используется картой на дашборде.",
)
def list_locations() -> list[LocationOut]:
    return [
        LocationOut(
            code=location.code,
            title=location.title,
            lat=location.lat,
            lon=location.lon,
            description=location.description,
        )
        for location in CAMPUS_LOCATIONS
    ]


@router.get(
    "/health",
    response_model=HealthOut,
    summary="Проверка работоспособности",
    description="Используется healthcheck'ом Docker Compose и мониторингом.",
)
def health(db: Annotated[Session, Depends(get_db)]) -> HealthOut:
    database = "ok"
    total = 0
    last_ts = None

    try:
        total = db.scalar(select(func.count()).select_from(Measurement)) or 0
        last_ts = db.scalar(select(func.max(Measurement.ts)))
    except SQLAlchemyError as exc:  # pragma: no cover - зависит от состояния БД
        database = f"error: {exc.__class__.__name__}"

    return HealthOut(
        status="ok" if database == "ok" else "degraded",
        version=__version__,
        database=database,
        measurements=total,
        last_measurement_ts=last_ts,
        active_model=registry.active_version(),
    )
