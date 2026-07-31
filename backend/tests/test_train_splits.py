"""Тесты разбиения на train/test по времени.

Главное, что здесь проверяется, — отсутствие утечки будущего: между концом
обучающего периода и началом тестового обязан быть зазор, равный
максимальному горизонту прогноза.
"""

from __future__ import annotations

import pandas as pd

from app.ml.train import time_based_splits


def timestamps(hours: int = 24 * 180) -> pd.Series:
    return pd.Series(pd.date_range("2026-01-01", periods=hours, freq="h"))


class TestTimeBasedSplits:
    def test_produces_requested_number_of_folds(self):
        splits = time_based_splits(timestamps(), n_splits=4, gap_hours=48)
        assert len(splits) == 4

    def test_train_is_always_before_test(self):
        series = timestamps()
        for train_mask, test_mask in time_based_splits(series, n_splits=4, gap_hours=48):
            assert series[train_mask].max() < series[test_mask].min()

    def test_gap_is_at_least_forecast_horizon(self):
        series = timestamps()
        gap = 48
        for train_mask, test_mask in time_based_splits(series, n_splits=4, gap_hours=gap):
            distance = series[test_mask].min() - series[train_mask].max()
            assert distance >= pd.Timedelta(hours=gap)

    def test_train_window_expands(self):
        series = timestamps()
        sizes = [int(train_mask.sum()) for train_mask, _ in time_based_splits(series, 4, 48)]
        assert sizes == sorted(sizes)
        assert len(set(sizes)) > 1

    def test_test_folds_do_not_overlap(self):
        series = timestamps()
        splits = time_based_splits(series, n_splits=4, gap_hours=48)
        ranges = [(series[mask].min(), series[mask].max()) for _, mask in splits]
        for earlier, later in zip(ranges, ranges[1:], strict=False):
            assert earlier[1] < later[0]

    def test_short_series_gives_no_folds(self):
        assert time_based_splits(timestamps(hours=50), n_splits=4, gap_hours=48) == []
