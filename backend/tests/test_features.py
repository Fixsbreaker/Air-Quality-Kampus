"""Тесты формирования признаков и обучающей выборки."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.ml.features import (
    BASE_FEATURES,
    FEATURE_COLUMNS,
    add_features,
    build_supervised,
)


@pytest.fixture
def frame() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=24 * 30, freq="h")
    rng = np.random.default_rng(42)
    base = 30 + 15 * np.sin(2 * np.pi * index.hour / 24)
    return pd.DataFrame(
        {
            "pm25": base + rng.normal(0, 2, len(index)),
            "pm10": base * 1.6 + rng.normal(0, 3, len(index)),
            "no2": rng.uniform(5, 40, len(index)),
            "o3": rng.uniform(10, 80, len(index)),
            "temp": rng.uniform(-15, 30, len(index)),
            "wind_speed": rng.uniform(0, 12, len(index)),
            "wind_dir": rng.uniform(0, 360, len(index)),
            "humidity": rng.uniform(20, 95, len(index)),
            "pressure": rng.uniform(890, 930, len(index)),
        },
        index=index,
    )


class TestAddFeatures:
    def test_all_declared_features_exist(self, frame):
        featured = add_features(frame)
        missing = [name for name in BASE_FEATURES if name not in featured.columns]
        assert missing == []

    def test_lag_is_previous_value(self, frame):
        featured = add_features(frame)
        assert featured["pm25_lag_1"].iloc[10] == pytest.approx(frame["pm25"].iloc[9])
        assert featured["pm25_lag_24"].iloc[30] == pytest.approx(frame["pm25"].iloc[6])

    def test_no_future_leak(self, frame):
        """Признаки в момент t не должны меняться от подмены будущего.

        Портим последние сутки ряда и проверяем, что признаки в середине
        остались прежними. Если бы где-то использовался center=True или
        отрицательный shift, значения бы поехали.
        """
        featured = add_features(frame)

        corrupted = frame.copy()
        corrupted.iloc[-24:, corrupted.columns.get_loc("pm25")] = 9999.0
        featured_corrupted = add_features(corrupted)

        checkpoint = len(frame) - 48
        for column in BASE_FEATURES:
            before = featured[column].iloc[checkpoint]
            after = featured_corrupted[column].iloc[checkpoint]
            assert before == pytest.approx(after, nan_ok=True), column

    def test_cyclic_encoding_is_bounded(self, frame):
        featured = add_features(frame)
        for column in ("hour_sin", "hour_cos", "wind_sin", "wind_cos", "month_sin", "month_cos"):
            assert featured[column].abs().max() <= 1.0 + 1e-9

    def test_heating_season_flag(self, frame):
        featured = add_features(frame)
        # Январь входит в отопительный сезон Алматы
        assert featured["heating_season"].unique().tolist() == [1]

    def test_empty_frame_is_passthrough(self):
        empty = pd.DataFrame()
        assert add_features(empty).empty


class TestBuildSupervised:
    def test_target_is_value_h_hours_ahead(self, frame):
        data = build_supervised(frame, horizons=(1, 6), location="main")
        row = data[(data["horizon"] == 6)].iloc[0]
        expected = frame.loc[row["ts"] + pd.Timedelta(hours=6), "pm25"]
        assert row["target"] == pytest.approx(expected)

    def test_target_ts_matches_horizon(self, frame):
        data = build_supervised(frame, horizons=(3,), location="main")
        deltas = (data["target_ts"] - data["ts"]).unique()
        assert list(deltas) == [pd.Timedelta(hours=3)]

    def test_persistence_baseline_is_current_value(self, frame):
        data = build_supervised(frame, horizons=(12,), location="main")
        row = data.iloc[0]
        assert row["baseline_persistence"] == pytest.approx(frame.loc[row["ts"], "pm25"])

    def test_location_one_hot(self, frame):
        data = build_supervised(frame, horizons=(1,), location="dorm_karimova")
        assert data["loc_dorm_karimova"].unique().tolist() == [1]
        assert data["loc_main"].unique().tolist() == [0]

    def test_all_model_features_present(self, frame):
        data = build_supervised(frame, horizons=(1, 24), location="main")
        missing = [name for name in FEATURE_COLUMNS if name not in data.columns]
        assert missing == []

    def test_rows_without_target_are_dropped(self, frame):
        data = build_supervised(frame, horizons=(48,), location="main")
        assert data["target"].isna().sum() == 0
        # Последние 48 часов не имеют цели и не должны попасть в выборку
        assert data["ts"].max() <= frame.index[-49]


class TestLoadFrame:
    """Регрессия: Open-Meteo вместе с фактом отдаёт собственный прогноз на
    двое суток вперёд, и эти строки лежат в той же таблице. Модель обязана
    видеть только уже наступившие часы."""

    def test_future_rows_are_cut_off(self, db):
        from app.ml.features import load_frame
        from app.models import utcnow
        from tests.conftest import make_measurement

        now = utcnow().replace(minute=0, second=0, microsecond=0)
        for offset in (-3, -2, -1, 0):
            db.add(make_measurement(now + pd.Timedelta(hours=offset).to_pytimedelta()))
        for offset in (1, 24, 48):
            db.add(make_measurement(now + pd.Timedelta(hours=offset).to_pytimedelta()))
        db.commit()

        frame = load_frame(db, "main", days=30)

        assert not frame.empty
        assert frame.index.max() <= pd.Timestamp(now)
        assert len(frame) == 4

    def test_explicit_until_is_respected(self, db):
        from app.ml.features import load_frame
        from app.models import utcnow
        from tests.conftest import make_measurement

        now = utcnow().replace(minute=0, second=0, microsecond=0)
        for offset in (-5, -4, -3, -2, -1):
            db.add(make_measurement(now + pd.Timedelta(hours=offset).to_pytimedelta()))
        db.commit()

        cutoff = now - pd.Timedelta(hours=3).to_pytimedelta()
        frame = load_frame(db, "main", days=30, until=cutoff)

        assert frame.index.max() <= pd.Timestamp(cutoff)
        assert len(frame) == 3
