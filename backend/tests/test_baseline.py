"""Тесты метрик и наивных моделей."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.ml.baseline import (
    best_baseline,
    evaluate,
    evaluate_baselines,
    mean_absolute_error,
    mean_absolute_percentage_error,
    metrics_by_horizon,
    persistence_prediction,
    root_mean_squared_error,
    seasonal_naive_prediction,
)


class TestMetrics:
    def test_mae_on_known_numbers(self):
        assert mean_absolute_error([1, 2, 3], [1, 2, 3]) == 0.0
        assert mean_absolute_error([10, 20], [12, 18]) == 2.0

    def test_rmse_penalises_large_errors_more(self):
        small = root_mean_squared_error([0, 0], [1, 1])
        large = root_mean_squared_error([0, 0], [0, 2])
        assert large > small

    def test_mape_skips_zero_actuals(self):
        value = mean_absolute_percentage_error([0.0, 100.0], [50.0, 110.0])
        assert value == pytest.approx(10.0)

    def test_mape_is_none_when_all_actuals_are_zero(self):
        assert mean_absolute_percentage_error([0.0, 0.0], [1.0, 1.0]) is None

    def test_evaluate_returns_rounded_values(self):
        metrics = evaluate([10.0, 20.0], [11.0, 19.0])
        assert metrics.mae == 1.0
        assert metrics.rmse == 1.0


@pytest.fixture
def data() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "horizon": [1, 1, 24, 24],
            "target": [30.0, 40.0, 50.0, 60.0],
            "baseline_persistence": [28.0, 44.0, 45.0, 70.0],
            "baseline_seasonal": [31.0, np.nan, 52.0, 58.0],
        }
    )


class TestBaselines:
    def test_persistence_uses_current_value(self, data):
        assert list(persistence_prediction(data)) == [28.0, 44.0, 45.0, 70.0]

    def test_seasonal_falls_back_to_persistence_on_gaps(self, data):
        predicted = seasonal_naive_prediction(data)
        assert predicted[1] == 44.0  # NaN заменён на persistence
        assert predicted[0] == 31.0

    def test_both_baselines_are_evaluated(self, data):
        scores = evaluate_baselines(data)
        assert set(scores) == {"persistence", "seasonal_naive"}

    def test_best_baseline_has_lowest_mae(self, data):
        name, metric = best_baseline(data)
        scores = evaluate_baselines(data)
        assert metric.mae == min(item.mae for item in scores.values())
        assert name in scores


class TestByHorizon:
    def test_split_by_horizon(self, data):
        predictions = np.array([30.0, 40.0, 50.0, 60.0])  # идеальный прогноз
        table = metrics_by_horizon(data, predictions)

        assert list(table.index) == [1, 24]
        assert table.loc[1, "mae_model"] == 0.0
        assert table.loc[1, "n"] == 2
        # Модель без ошибок обязана обыгрывать persistence на 100 %
        assert table.loc[1, "improvement_pct"] == 100.0
