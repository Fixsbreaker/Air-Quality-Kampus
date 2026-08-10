"""Обучение модели прогноза PM2.5.

Валидация — расширяющееся окно по времени (TimeSeriesSplit по смыслу, но
реализовано вручную, потому что нужен зазор между обучением и тестом).

Почему зазор обязателен: строка за момент t с горизонтом 48 имеет цель в
момент t+48. Если тест начинается сразу после конца обучения, часть целей
обучающих строк попадёт внутрь тестового периода — это утечка будущего.
Поэтому между train и test выбрасывается окно длиной в максимальный
горизонт прогноза.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.config import settings
from app.ml import registry
from app.ml.baseline import Metrics, best_baseline, evaluate, evaluate_baselines, metrics_by_horizon
from app.ml.features import FEATURE_COLUMNS, build_dataset
from app.models import ModelRun

logger = logging.getLogger(__name__)

MIN_TRAIN_ROWS = 2000
DEFAULT_SPLITS = 4

# OSError ловится намеренно: на macOS без установленного libomp пакет
# lightgbm импортируется, но падает при загрузке нативной библиотеки.
# В этом случае молча переходим на HistGradientBoostingRegressor из
# scikit-learn — алгоритм тот же по сути, зато без внешних зависимостей.
try:  # pragma: no cover - зависит от окружения
    from lightgbm import LGBMRegressor

    HAS_LIGHTGBM = True
except (ImportError, OSError) as exc:  # pragma: no cover
    from sklearn.ensemble import HistGradientBoostingRegressor

    HAS_LIGHTGBM = False
    logger.warning(
        "LightGBM недоступен (%s) — используется HistGradientBoostingRegressor", exc
    )


@dataclass
class TrainReport:
    version: str
    algorithm: str
    rows_used: int
    cv_metrics: dict[str, float]
    baseline_metrics: dict[str, dict[str, float | None]]
    best_baseline_name: str
    improvement_pct: float
    folds: list[dict[str, Any]] = field(default_factory=list)
    by_horizon: dict[str, Any] = field(default_factory=dict)
    beats_baseline: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "algorithm": self.algorithm,
            "rows_used": self.rows_used,
            "cv_metrics": self.cv_metrics,
            "baseline_metrics": self.baseline_metrics,
            "best_baseline": self.best_baseline_name,
            "improvement_pct": self.improvement_pct,
            "beats_baseline": self.beats_baseline,
            "folds": self.folds,
            "by_horizon": self.by_horizon,
        }


def make_model() -> Any:
    """Регрессор с параметрами, подобранными под часовой ряд PM2.5."""
    if HAS_LIGHTGBM:
        return LGBMRegressor(
            objective="regression_l1",  # L1 устойчивее к пикам концентрации
            n_estimators=600,
            learning_rate=0.05,
            num_leaves=63,
            min_child_samples=40,
            subsample=0.9,
            subsample_freq=1,
            colsample_bytree=0.8,
            reg_lambda=1.0,
            n_jobs=-1,
            verbose=-1,
            random_state=42,
        )
    return HistGradientBoostingRegressor(  # pragma: no cover - запасной вариант
        loss="absolute_error",
        max_iter=400,
        learning_rate=0.05,
        max_leaf_nodes=63,
        random_state=42,
    )


def time_based_splits(
    timestamps: pd.Series, n_splits: int = DEFAULT_SPLITS, gap_hours: int = 48
) -> list[tuple[pd.Series, pd.Series]]:
    """Расширяющееся окно: train — всё прошлое, test — следующий блок.

    Возвращает список пар булевых масок (train, test).
    """
    unique = np.sort(timestamps.unique())
    total = len(unique)
    if total < (n_splits + 1) * 24:
        return []

    fold_size = total // (n_splits + 1)
    gap = pd.Timedelta(hours=gap_hours)
    splits: list[tuple[pd.Series, pd.Series]] = []

    for fold in range(1, n_splits + 1):
        test_start = unique[fold * fold_size]
        test_end = unique[(fold + 1) * fold_size - 1] if fold < n_splits else unique[-1]
        train_end = pd.Timestamp(test_start) - gap

        train_mask = timestamps <= train_end
        test_mask = (timestamps >= test_start) & (timestamps <= test_end)

        if train_mask.sum() < MIN_TRAIN_ROWS // 4 or test_mask.sum() == 0:
            continue
        splits.append((train_mask, test_mask))

    return splits


def cross_validate(data: pd.DataFrame, n_splits: int = DEFAULT_SPLITS) -> tuple[list[dict], Metrics]:
    """Прогнать кросс-валидацию и вернуть пофолдовые и усреднённые метрики."""
    horizon_gap = int(data["horizon"].max())
    splits = time_based_splits(data["ts"], n_splits=n_splits, gap_hours=horizon_gap)
    if not splits:
        raise ValueError("Недостаточно истории для кросс-валидации по времени")

    features = list(FEATURE_COLUMNS)
    fold_reports: list[dict] = []
    all_true: list[np.ndarray] = []
    all_pred: list[np.ndarray] = []

    for index, (train_mask, test_mask) in enumerate(splits, start=1):
        train = data[train_mask]
        test = data[test_mask]

        model = make_model()
        model.fit(train[features], train["target"])
        predictions = np.clip(model.predict(test[features]), 0, None)

        model_metrics = evaluate(test["target"], predictions)
        baselines = evaluate_baselines(test)

        fold_reports.append(
            {
                "fold": index,
                "train_rows": int(len(train)),
                "test_rows": int(len(test)),
                "test_from": str(test["ts"].min()),
                "test_to": str(test["ts"].max()),
                "model": model_metrics.as_dict(),
                "baselines": {name: metric.as_dict() for name, metric in baselines.items()},
            }
        )
        all_true.append(test["target"].to_numpy(dtype=float))
        all_pred.append(predictions)

        logger.info(
            "Фолд %s: MAE модели %.3f, MAE persistence %.3f",
            index,
            model_metrics.mae,
            baselines["persistence"].mae,
        )

    overall = evaluate(np.concatenate(all_true), np.concatenate(all_pred))
    return fold_reports, overall


def train(
    db: Session,
    *,
    horizon: int | None = None,
    days: int | None = None,
    n_splits: int = DEFAULT_SPLITS,
    activate: bool = True,
) -> TrainReport:
    """Полный цикл: выборка → кросс-валидация → финальное обучение → реестр."""
    horizon = horizon or settings.forecast_horizon_hours
    days = days or settings.train_history_days
    horizons = range(1, horizon + 1)

    data = build_dataset(db, horizons=horizons, days=days)
    if data.empty:
        raise ValueError("В базе нет данных. Сначала выполните backfill.")
    if len(data) < MIN_TRAIN_ROWS:
        raise ValueError(
            f"Недостаточно данных для обучения: {len(data)} строк, нужно минимум {MIN_TRAIN_ROWS}. "
            "Запустите: python -m scripts.backfill --days 730"
        )

    logger.info("Обучающая выборка: %s строк, %s признаков", len(data), len(FEATURE_COLUMNS))

    folds, cv_metrics = cross_validate(data, n_splits=n_splits)

    # Сравнение с baseline считаем на объединении тестовых периодов —
    # ровно на тех строках, которые модель не видела при обучении.
    test_mask = pd.Series(False, index=data.index)
    horizon_gap = int(data["horizon"].max())
    for _, fold_test_mask in time_based_splits(data["ts"], n_splits, horizon_gap):
        test_mask |= fold_test_mask
    holdout = data[test_mask]

    baselines = evaluate_baselines(holdout)
    baseline_name, baseline_metric = best_baseline(holdout)
    improvement = (baseline_metric.mae - cv_metrics.mae) / baseline_metric.mae * 100

    algorithm = "lightgbm" if HAS_LIGHTGBM else "hist-gbr"
    version = registry.new_version(algorithm)

    final_model = make_model()
    final_model.fit(data[list(FEATURE_COLUMNS)], data["target"])

    # Разбивка ошибки по горизонтам — на последнем фолде, для графика в отчёте.
    last_train_mask, last_test_mask = time_based_splits(data["ts"], n_splits, horizon_gap)[-1]
    eval_model = make_model()
    eval_model.fit(data[last_train_mask][list(FEATURE_COLUMNS)], data[last_train_mask]["target"])
    last_test = data[last_test_mask]
    by_horizon = metrics_by_horizon(
        last_test, np.clip(eval_model.predict(last_test[list(FEATURE_COLUMNS)]), 0, None)
    )

    report = TrainReport(
        version=version,
        algorithm=algorithm,
        rows_used=int(len(data)),
        cv_metrics=cv_metrics.as_dict(),
        baseline_metrics={name: metric.as_dict() for name, metric in baselines.items()},
        best_baseline_name=baseline_name,
        improvement_pct=round(improvement, 2),
        folds=folds,
        by_horizon=by_horizon.reset_index().to_dict(orient="records"),
        beats_baseline=cv_metrics.mae < baseline_metric.mae,
    )

    metadata = registry.ModelMetadata(
        version=version,
        algorithm=algorithm,
        trained_at=datetime.now(UTC).isoformat(),
        rows_used=report.rows_used,
        horizons=list(horizons),
        feature_columns=list(FEATURE_COLUMNS),
        metrics=report.cv_metrics,
        baseline_metrics=report.baseline_metrics,
        notes=(
            f"Лучший baseline: {baseline_name}, MAE {baseline_metric.mae}. "
            f"Улучшение модели: {report.improvement_pct}%."
        ),
    )
    registry.save_model(final_model, metadata, activate=activate and report.beats_baseline)

    if not report.beats_baseline:
        logger.warning(
            "Модель не превзошла baseline (MAE %.3f против %.3f) — активная версия не изменена",
            cv_metrics.mae,
            baseline_metric.mae,
        )

    _record_run(db, report, activate=activate and report.beats_baseline)
    return report


def _record_run(db: Session, report: TrainReport, *, activate: bool) -> None:
    """Сохранить результат обучения в model_runs — история для отчёта."""
    if activate:
        db.execute(update(ModelRun).values(is_active=False))

    baseline = report.baseline_metrics[report.best_baseline_name]
    db.add(
        ModelRun(
            model_version=report.version,
            algorithm=report.algorithm,
            rows_used=report.rows_used,
            mae=report.cv_metrics["mae"],
            rmse=report.cv_metrics["rmse"],
            baseline_mae=baseline["mae"],
            baseline_rmse=baseline["rmse"],
            is_active=activate,
            notes=(
                f"baseline={report.best_baseline_name}; "
                f"improvement={report.improvement_pct}%; folds={len(report.folds)}"
            ),
        )
    )
    db.commit()
