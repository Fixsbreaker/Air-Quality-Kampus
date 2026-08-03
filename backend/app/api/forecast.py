"""GET /api/forecast — прогноз PM2.5/AQI на ближайшие часы."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import location_dep
from app.locations import CampusLocation
from app.ml.predict import latest_forecast
from app.schemas import ForecastOut, ForecastPointOut

router = APIRouter(prefix="/api", tags=["Прогноз"])


@router.get(
    "/forecast",
    response_model=ForecastOut,
    summary="Прогноз качества воздуха",
    description=(
        "Прогноз читается из таблицы forecasts, куда его записывает фоновая "
        "задача. API не запускает модель на лету — так ответ остаётся быстрым, "
        "а тяжёлые вычисления не блокируют веб-процесс."
    ),
)
def get_forecast(
    db: Annotated[Session, Depends(get_db)],
    location: Annotated[CampusLocation, Depends(location_dep)],
    hours: Annotated[int, Query(ge=1, le=168, description="Глубина прогноза в часах")] = 48,
) -> ForecastOut:
    rows = latest_forecast(db, location.code, hours=hours)

    if not rows:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=(
                f"Прогноз для локации '{location.code}' ещё не рассчитан. "
                "Выполните: python -m scripts.train && python -m scripts.make_forecast"
            ),
        )

    points = [ForecastPointOut.model_validate(row) for row in rows]
    worst = max(points, key=lambda point: point.aqi_pred)

    return ForecastOut(
        location=location.code,
        model_version=rows[0].model_version,
        generated_at=rows[0].created_at,
        horizon_hours=min(hours, settings.forecast_horizon_hours),
        points=points,
        worst=worst,
    )
