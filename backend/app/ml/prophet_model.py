"""Альтернативная модель — Prophet.

В ТЗ Prophet заявлен как промежуточная ступень между baseline и LightGBM.
Библиотека тяжёлая (тянет компилятор Stan), поэтому вынесена в отдельный
файл зависимостей requirements-prophet.txt и импортируется лениво: если
пакета нет, обучение продолжается на LightGBM, а функция сообщает об этом
явным исключением ProphetUnavailable.

Prophet работает как «одна модель на локацию» и не умеет использовать
лаговые признаки, зато хорошо ловит суточную и годовую сезонность —
поэтому он оставлен как точка сравнения, а не как основная модель.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.ml.baseline import Metrics, evaluate

logger = logging.getLogger(__name__)


class ProphetUnavailable(RuntimeError):
    """Prophet не установлен в текущем окружении."""


@dataclass
class ProphetResult:
    metrics: Metrics
    forecast: pd.DataFrame


def _load_prophet():
    try:
        from prophet import Prophet
    except ImportError as exc:  # pragma: no cover - зависит от окружения
        raise ProphetUnavailable(
            "Prophet не установлен. Установите: pip install -r requirements-prophet.txt"
        ) from exc
    return Prophet


def prepare_series(frame: pd.DataFrame, column: str = "pm25") -> pd.DataFrame:
    """Prophet ждёт две колонки: ds (время) и y (значение)."""
    series = frame[[column]].dropna().reset_index()
    series.columns = ["ds", "y"]
    return series


def fit_predict(
    frame: pd.DataFrame,
    horizon_hours: int = 48,
    weather: pd.DataFrame | None = None,
) -> ProphetResult:
    """Обучить Prophet на истории и оценить его на последнем окне.

    Последние horizon_hours часов держатся как отложенная выборка, чтобы
    метрику можно было сравнить с LightGBM на одном и том же периоде.
    """
    Prophet = _load_prophet()

    series = prepare_series(frame)
    if len(series) < horizon_hours * 4:
        raise ValueError("Слишком короткий ряд для Prophet")

    train = series.iloc[:-horizon_hours]
    test = series.iloc[-horizon_hours:]

    model = Prophet(
        daily_seasonality=True,
        weekly_seasonality=True,
        yearly_seasonality=True,
        changepoint_prior_scale=0.05,
        interval_width=0.8,
    )

    if weather is not None and "temp" in weather:
        model.add_regressor("temp")
        train = train.merge(
            weather[["temp"]].reset_index().rename(columns={"ts": "ds"}), on="ds", how="left"
        )
        train["temp"] = train["temp"].ffill().bfill()

    model.fit(train)

    future = model.make_future_dataframe(periods=horizon_hours, freq="h")
    if weather is not None and "temp" in weather:
        future = future.merge(
            weather[["temp"]].reset_index().rename(columns={"ts": "ds"}), on="ds", how="left"
        )
        future["temp"] = future["temp"].ffill().bfill()

    forecast = model.predict(future)
    predicted = forecast.set_index("ds").loc[test["ds"], "yhat"].to_numpy()
    predicted = np.clip(predicted, 0, None)

    metrics = evaluate(test["y"].to_numpy(dtype=float), predicted)
    logger.info("Prophet: MAE %.3f, RMSE %.3f", metrics.mae, metrics.rmse)
    return ProphetResult(metrics=metrics, forecast=forecast)
