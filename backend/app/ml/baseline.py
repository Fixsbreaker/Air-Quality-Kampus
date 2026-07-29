"""Наивные модели и метрики качества.

Смысл baseline: любая ML-модель должна быть заметно лучше «завтра как
сегодня». Если она не лучше — модель бесполезна, и это тоже результат,
который честно фиксируется в отчёте (ТЗ, раздел «Риски»).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Metrics:
    mae: float
    rmse: float
    mape: float | None = None

    def as_dict(self) -> dict[str, float | None]:
        return {"mae": self.mae, "rmse": self.rmse, "mape": self.mape}


def mean_absolute_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(y_true) - np.asarray(y_pred))))


def root_mean_squared_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    diff = np.asarray(y_true) - np.asarray(y_pred)
    return float(np.sqrt(np.mean(diff**2)))


def mean_absolute_percentage_error(y_true: np.ndarray, y_pred: np.ndarray) -> float | None:
    """MAPE считается только по точкам с ненулевой фактической концентрацией."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = np.abs(y_true) > 1e-6
    if not mask.any():
        return None
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def evaluate(y_true, y_pred) -> Metrics:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return Metrics(
        mae=round(mean_absolute_error(y_true, y_pred), 4),
        rmse=round(root_mean_squared_error(y_true, y_pred), 4),
        mape=(
            round(value, 2)
            if (value := mean_absolute_percentage_error(y_true, y_pred)) is not None
            else None
        ),
    )


def persistence_prediction(data: pd.DataFrame) -> np.ndarray:
    """Наивный прогноз «через h часов будет столько же, сколько сейчас»."""
    return data["baseline_persistence"].to_numpy(dtype=float)


def seasonal_naive_prediction(data: pd.DataFrame) -> np.ndarray:
    """Наивный прогноз «будет как в тот же час предыдущих суток».

    Там, где сезонное значение отсутствует, честно откатываемся к persistence,
    иначе метрика считалась бы по разному числу точек.
    """
    seasonal = data["baseline_seasonal"].to_numpy(dtype=float)
    fallback = persistence_prediction(data)
    return np.where(np.isnan(seasonal), fallback, seasonal)


def evaluate_baselines(data: pd.DataFrame) -> dict[str, Metrics]:
    y_true = data["target"].to_numpy(dtype=float)
    return {
        "persistence": evaluate(y_true, persistence_prediction(data)),
        "seasonal_naive": evaluate(y_true, seasonal_naive_prediction(data)),
    }


def best_baseline(data: pd.DataFrame) -> tuple[str, Metrics]:
    """Наиболее сильный наивный прогноз — с ним и сравниваем модель."""
    scores = evaluate_baselines(data)
    name = min(scores, key=lambda key: scores[key].mae)
    return name, scores[name]


def metrics_by_horizon(data: pd.DataFrame, predictions: np.ndarray) -> pd.DataFrame:
    """Разбивка ошибки по горизонтам — для графика в отчёте."""
    frame = data[["horizon", "target"]].copy()
    frame["pred"] = predictions
    frame["baseline"] = persistence_prediction(data)

    grouped = frame.groupby("horizon").apply(
        lambda part: pd.Series(
            {
                "mae_model": mean_absolute_error(part["target"], part["pred"]),
                "rmse_model": root_mean_squared_error(part["target"], part["pred"]),
                "mae_baseline": mean_absolute_error(part["target"], part["baseline"]),
                "n": len(part),
            }
        ),
        include_groups=False,
    )
    grouped["improvement_pct"] = (
        (grouped["mae_baseline"] - grouped["mae_model"]) / grouped["mae_baseline"] * 100
    ).round(2)
    return grouped.round(3)
