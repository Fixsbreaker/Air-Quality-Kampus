"""Боевой прогноз: активная модель → таблица forecasts.

Для каждой точки кампуса берётся последний доступный час, по нему строится
вектор признаков, и модель вызывается по одному разу на каждый горизонт
1…48. Результат переводится в AQI и категорию — дашборд и бот получают уже
готовый ответ, без вычислений на стороне клиента.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.cache import get_cache
from app.config import settings
from app.locations import CAMPUS_LOCATIONS
from app.ml import registry
from app.ml.features import FEATURE_COLUMNS, add_features, load_frame
from app.models import Forecast, utcnow
from app.services.aqi import aqi_from_pm25, category_of

logger = logging.getLogger(__name__)

# Истории на две недели с запасом хватает для лага 48 и окна 24.
HISTORY_DAYS_FOR_PREDICT = 14


@dataclass
class ForecastPoint:
    target_ts: datetime
    horizon_h: int
    pm25_pred: float
    aqi_pred: int
    aqi_category: str


def _feature_matrix(
    frame: pd.DataFrame, location: str, horizons: range
) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Один и тот же вектор признаков, размноженный по горизонтам.

    Возвращает матрицу признаков и метку времени последнего наблюдения —
    от неё отсчитываются целевые моменты прогноза.
    """
    from app.ml.features import BASE_FEATURES, LOCATION_CODES, REQUIRED_FEATURES

    featured = add_features(frame).dropna(subset=list(REQUIRED_FEATURES))
    if featured.empty:
        raise ValueError(f"Недостаточно истории для прогноза по локации {location}")

    last = featured.iloc[[-1]][list(BASE_FEATURES)]
    matrix = pd.concat([last] * len(horizons), ignore_index=True)
    matrix["horizon"] = list(horizons)
    for code in LOCATION_CODES:
        matrix[f"loc_{code}"] = int(code == location)

    return matrix[list(FEATURE_COLUMNS)], featured.index[-1]


def predict_location(
    db: Session, location_code: str, model=None, model_version: str | None = None
) -> list[ForecastPoint]:
    """Посчитать прогноз на FORECAST_HORIZON_HOURS вперёд для одной точки."""
    if model is None:
        model, metadata = registry.load_active()
        model_version = metadata.version
    if model_version is None:
        model_version = registry.active_version() or "unknown"

    horizons = range(1, settings.forecast_horizon_hours + 1)
    frame = load_frame(db, location_code, days=HISTORY_DAYS_FOR_PREDICT)
    if frame.empty:
        raise ValueError(f"Нет данных по локации {location_code}")

    matrix, last_ts = _feature_matrix(frame, location_code, horizons)
    predictions = np.clip(model.predict(matrix), 0, None)

    points: list[ForecastPoint] = []
    for horizon, value in zip(horizons, predictions, strict=True):
        pm25 = round(float(value), 2)
        aqi = aqi_from_pm25(pm25) or 0
        points.append(
            ForecastPoint(
                target_ts=(last_ts + timedelta(hours=horizon)).to_pydatetime(),
                horizon_h=horizon,
                pm25_pred=pm25,
                aqi_pred=aqi,
                aqi_category=category_of(aqi),
            )
        )
    return points


def store_forecast(
    db: Session, location_code: str, points: list[ForecastPoint], model_version: str
) -> int:
    """Перезаписать прогноз этой версии модели для указанной локации."""
    if not points:
        return 0

    horizon_start = min(point.target_ts for point in points)
    db.execute(
        delete(Forecast).where(
            Forecast.location == location_code,
            Forecast.model_version == model_version,
            Forecast.target_ts >= horizon_start,
        )
    )

    now = utcnow()
    db.add_all(
        Forecast(
            created_at=now,
            target_ts=point.target_ts,
            location=location_code,
            horizon_h=point.horizon_h,
            pm25_pred=point.pm25_pred,
            aqi_pred=point.aqi_pred,
            aqi_category=point.aqi_category,
            model_version=model_version,
        )
        for point in points
    )
    db.commit()
    return len(points)


def refresh_all(db: Session) -> dict[str, int]:
    """Пересчитать прогноз по всем точкам кампуса. Ошибка одной точки не
    останавливает остальные — так один пустой датасет не роняет весь job."""
    model, metadata = registry.load_active()
    written: dict[str, int] = {}

    for location in CAMPUS_LOCATIONS:
        try:
            points = predict_location(db, location.code, model=model, model_version=metadata.version)
            written[location.code] = store_forecast(db, location.code, points, metadata.version)
        except ValueError as exc:
            logger.warning("Прогноз для %s пропущен: %s", location.code, exc)
            written[location.code] = 0

    # Прогноз пересчитан — сбрасываем кэшированные ответы эндпоинта.
    get_cache().delete_prefix("aqi:forecast")

    logger.info("Прогноз обновлён (%s): %s", metadata.version, written)
    return written


def latest_forecast(db: Session, location_code: str, hours: int | None = None) -> list[Forecast]:
    """Прочитать актуальный прогноз из базы для API и бота."""
    hours = hours or settings.forecast_horizon_hours
    now = utcnow()
    stmt = (
        select(Forecast)
        .where(
            Forecast.location == location_code,
            Forecast.target_ts >= now,
            Forecast.target_ts <= now + timedelta(hours=hours),
        )
        .order_by(Forecast.target_ts)
    )
    rows = list(db.scalars(stmt).all())

    # На случай нескольких версий в таблице — оставляем самую свежую.
    if rows:
        newest = max(row.created_at for row in rows)
        rows = [row for row in rows if row.created_at == newest]
    return rows
