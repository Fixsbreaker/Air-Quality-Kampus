"""Формирование признаков для прогноза PM2.5.

Постановка задачи — прямое многогоризонтное прогнозирование (direct
multi-horizon): вместо 48 отдельных моделей обучается одна, а номер
горизонта подаётся ей как признак. Такой подход даёт больше обучающих
примеров и сохраняет одну версию модели в реестре.

Все признаки рассчитываются строго по прошлому относительно момента t:
лаги, скользящие статистики и календарь. Заглядывания в будущее нет —
это проверяется тестом test_features.py::test_no_future_leak.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.locations import CAMPUS_LOCATIONS
from app.models import Measurement, Weather, utcnow

logger = logging.getLogger(__name__)

TARGET = "pm25"
SOURCE = "open-meteo"

LAGS = (1, 2, 3, 6, 12, 24, 48)
ROLLING_WINDOWS = (3, 6, 24)

WEATHER_COLUMNS = ("temp", "wind_speed", "humidity", "pressure")

LOCATION_CODES = tuple(loc.code for loc in CAMPUS_LOCATIONS)


def load_frame(
    db: Session, location: str, days: int = 730, until: datetime | None = None
) -> pd.DataFrame:
    """Собрать часовой ряд «загрязнение + погода» по одной точке кампуса.

    Верхняя граница `until` по умолчанию равна текущему моменту, и это
    принципиально. Open-Meteo вместе с прошлым отдаёт собственный прогноз на
    двое суток вперёд, и эти строки тоже лежат в measurements (позже они
    перезаписываются фактическими значениями). Без отсечки модель приняла бы
    чужой прогноз за наблюдение: обучалась бы на нём и строила бы свой прогноз
    от точки, которая ещё не наступила.
    """
    now = utcnow()
    since = now - timedelta(days=days)
    until = until or now

    stmt = (
        select(
            Measurement.ts,
            Measurement.pm25,
            Measurement.pm10,
            Measurement.no2,
            Measurement.o3,
            Weather.temp,
            Weather.wind_speed,
            Weather.wind_dir,
            Weather.humidity,
            Weather.pressure,
        )
        .select_from(Measurement)
        .outerjoin(
            Weather,
            (Weather.ts == Measurement.ts) & (Weather.location == Measurement.location),
        )
        .where(
            Measurement.location == location,
            Measurement.source == SOURCE,
            Measurement.ts >= since,
            Measurement.ts <= until,
        )
        .order_by(Measurement.ts)
    )

    rows = db.execute(stmt).all()
    frame = pd.DataFrame(rows, columns=[
        "ts", "pm25", "pm10", "no2", "o3",
        "temp", "wind_speed", "wind_dir", "humidity", "pressure",
    ])

    if frame.empty:
        return frame

    frame["ts"] = pd.to_datetime(frame["ts"])
    frame = frame.drop_duplicates(subset="ts").sort_values("ts").set_index("ts")

    # Выравниваем ряд по часовой сетке — пропуски станут явными NaN.
    full_index = pd.date_range(frame.index.min(), frame.index.max(), freq="h")
    frame = frame.reindex(full_index)
    frame.index.name = "ts"
    frame["location"] = location
    return frame


def add_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Добавить лаги, скользящие статистики, погодные и календарные признаки."""
    if frame.empty:
        return frame

    out = frame.copy().sort_index()

    out["pm25_now"] = out[TARGET]
    out["pm10_now"] = out["pm10"]

    for lag in LAGS:
        out[f"pm25_lag_{lag}"] = out[TARGET].shift(lag)
    out["pm10_lag_1"] = out["pm10"].shift(1)
    out["pm10_lag_24"] = out["pm10"].shift(24)

    for window in ROLLING_WINDOWS:
        rolled = out[TARGET].rolling(window=window, min_periods=max(2, window // 2))
        out[f"pm25_roll_mean_{window}"] = rolled.mean()
        out[f"pm25_roll_std_{window}"] = rolled.std()
        out[f"pm25_roll_max_{window}"] = rolled.max()

    out["pm25_diff_1"] = out[TARGET].diff(1)
    out["pm25_diff_24"] = out[TARGET].diff(24)
    out["pm25_ratio_24"] = out[TARGET] / out["pm25_roll_mean_24"].replace(0, np.nan)

    # Ветер — циклическая величина, поэтому раскладывается на синус и косинус.
    wind_rad = np.deg2rad(out["wind_dir"].astype(float))
    out["wind_sin"] = np.sin(wind_rad)
    out["wind_cos"] = np.cos(wind_rad)

    hours = out.index.hour
    out["hour_sin"] = np.sin(2 * np.pi * hours / 24)
    out["hour_cos"] = np.cos(2 * np.pi * hours / 24)
    out["dow"] = out.index.dayofweek
    out["is_weekend"] = (out.index.dayofweek >= 5).astype(int)
    out["month"] = out.index.month
    out["month_sin"] = np.sin(2 * np.pi * out.index.month / 12)
    out["month_cos"] = np.cos(2 * np.pi * out.index.month / 12)

    # Отопительный сезон в Алматы — главный сезонный драйвер PM2.5.
    out["heating_season"] = out.index.month.isin([10, 11, 12, 1, 2, 3]).astype(int)

    return out


BASE_FEATURES: tuple[str, ...] = (
    "pm25_now",
    "pm10_now",
    *[f"pm25_lag_{lag}" for lag in LAGS],
    "pm10_lag_1",
    "pm10_lag_24",
    *[f"pm25_roll_{stat}_{w}" for w in ROLLING_WINDOWS for stat in ("mean", "std", "max")],
    "pm25_diff_1",
    "pm25_diff_24",
    "pm25_ratio_24",
    *WEATHER_COLUMNS,
    "wind_sin",
    "wind_cos",
    "hour_sin",
    "hour_cos",
    "dow",
    "is_weekend",
    "month_sin",
    "month_cos",
    "heating_season",
)

FEATURE_COLUMNS: tuple[str, ...] = (*BASE_FEATURES, "horizon", *[f"loc_{code}" for code in LOCATION_CODES])

REQUIRED_FEATURES: tuple[str, ...] = ("pm25_now", "pm25_lag_1", "pm25_lag_24", "pm25_roll_mean_24")


def build_supervised(
    frame: pd.DataFrame, horizons: range | tuple[int, ...], location: str
) -> pd.DataFrame:
    """Развернуть ряд в обучающую выборку «признаки → цель через h часов».

    Дополнительно кладутся две колонки-эталона:
      * baseline_persistence — «через h часов будет как сейчас»;
      * baseline_seasonal    — значение в тот же час предыдущих суток.
    Они нужны, чтобы честно сравнить модель с наивным прогнозом.
    """
    if frame.empty:
        return pd.DataFrame()

    featured = add_features(frame)
    parts: list[pd.DataFrame] = []

    for horizon in horizons:
        part = featured[list(BASE_FEATURES)].copy()
        part["horizon"] = horizon
        part["target"] = featured[TARGET].shift(-horizon)
        part["target_ts"] = featured.index + pd.to_timedelta(horizon, unit="h")
        part["baseline_persistence"] = featured[TARGET]
        # (24 - h) % 24 — сдвиг до того же часа суток, но строго в прошлом.
        part["baseline_seasonal"] = featured[TARGET].shift((24 - horizon) % 24)
        parts.append(part)

    data = pd.concat(parts)
    data.index.name = "ts"
    data = data.reset_index()

    for code in LOCATION_CODES:
        data[f"loc_{code}"] = int(code == location)

    data = data.dropna(subset=["target", *REQUIRED_FEATURES])
    return data.sort_values(["ts", "horizon"]).reset_index(drop=True)


def build_dataset(
    db: Session, horizons: range | tuple[int, ...], days: int = 730
) -> pd.DataFrame:
    """Обучающая выборка по всем точкам кампуса сразу.

    Одна общая модель на все локации: данных больше, а различия между
    точками модель ловит через one-hot признаки loc_*.
    """
    frames: list[pd.DataFrame] = []
    seen_series: dict[str, str] = {}

    for location in CAMPUS_LOCATIONS:
        raw = load_frame(db, location.code, days=days)
        if raw.empty:
            logger.warning("Нет данных для локации %s", location.code)
            continue

        # Источник считает воздух по сетке, и несколько объектов университета
        # попадают в одну её ячейку. Обучаться на копиях одного ряда бесполезно:
        # объём выборки растёт, а информации в ней не прибавляется. Одинаковые
        # ряды отсеиваются по хешу значений целевой переменной.
        fingerprint = pd.util.hash_pandas_object(raw[TARGET].fillna(-1), index=True).sum()
        key = str(fingerprint)
        if key in seen_series:
            logger.info(
                "Локация %s дублирует ряд %s (общая ячейка сетки источника) — пропущена",
                location.code,
                seen_series[key],
            )
            continue
        seen_series[key] = location.code

        supervised = build_supervised(raw, horizons, location.code)
        if not supervised.empty:
            frames.append(supervised)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames).sort_values(["ts", "horizon"]).reset_index(drop=True)


def latest_feature_row(frame: pd.DataFrame, location: str, horizon: int) -> pd.DataFrame:
    """Признаки на последний доступный час — вход для боевого прогноза."""
    featured = add_features(frame)
    featured = featured.dropna(subset=list(REQUIRED_FEATURES))
    if featured.empty:
        raise ValueError(f"Недостаточно истории для прогноза по локации {location}")

    row = featured.iloc[[-1]][list(BASE_FEATURES)].copy()
    row["horizon"] = horizon
    for code in LOCATION_CODES:
        row[f"loc_{code}"] = int(code == location)
    return row[list(FEATURE_COLUMNS)]
