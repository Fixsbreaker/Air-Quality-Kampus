"""Тесты очистки часового ряда."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.ingestion.cleaning import (
    clean_air_quality,
    drop_duplicates,
    enforce_physical_limits,
    interpolate_gaps,
    remove_outliers,
)
from app.ingestion.openmeteo import AirQualityRecord

START = datetime(2026, 1, 1, 0, 0)


def series(values: list[float | None], start: datetime = START) -> list[AirQualityRecord]:
    return [
        AirQualityRecord(ts=start + timedelta(hours=i), pm25=value, pm10=None, no2=None, o3=None)
        for i, value in enumerate(values)
    ]


class TestDuplicates:
    def test_last_record_wins(self):
        records = [
            AirQualityRecord(ts=START, pm25=10, pm10=None, no2=None, o3=None),
            AirQualityRecord(ts=START, pm25=20, pm10=None, no2=None, o3=None),
        ]
        cleaned, removed = drop_duplicates(records)
        assert removed == 1
        assert cleaned[0].pm25 == 20

    def test_result_is_sorted(self):
        records = [
            AirQualityRecord(ts=START + timedelta(hours=2), pm25=1, pm10=None, no2=None, o3=None),
            AirQualityRecord(ts=START, pm25=2, pm10=None, no2=None, o3=None),
        ]
        cleaned, _ = drop_duplicates(records)
        assert [item.ts for item in cleaned] == [START, START + timedelta(hours=2)]


class TestPhysicalLimits:
    def test_negative_becomes_none(self):
        cleaned, removed = enforce_physical_limits(series([-5.0, 10.0]))
        assert removed == 1
        assert cleaned[0].pm25 is None
        assert cleaned[1].pm25 == 10.0

    def test_absurdly_high_becomes_none(self):
        cleaned, removed = enforce_physical_limits(series([5000.0]))
        assert removed == 1
        assert cleaned[0].pm25 is None

    def test_valid_values_untouched(self):
        cleaned, removed = enforce_physical_limits(series([0.0, 42.0, 999.0]))
        assert removed == 0
        assert [item.pm25 for item in cleaned] == [0.0, 42.0, 999.0]


class TestOutliers:
    def test_single_spike_removed(self):
        values = [20.0] * 30
        values[15] = 900.0
        cleaned, removed = remove_outliers(series(values))
        assert removed == 1
        assert cleaned[15].pm25 is None

    def test_smooth_series_survives(self):
        values = [20.0 + (i % 5) for i in range(40)]
        _, removed = remove_outliers(series(values))
        assert removed == 0

    def test_short_series_is_not_touched(self):
        # На пяти точках оценка медианы и MAD недостоверна
        _, removed = remove_outliers(series([10.0, 11.0, 500.0, 12.0, 13.0]))
        assert removed == 0


class TestGaps:
    def test_short_gap_is_interpolated_linearly(self):
        cleaned, filled = interpolate_gaps(series([10.0, None, None, 40.0]))
        assert filled == 2
        assert cleaned[1].pm25 == 20.0
        assert cleaned[2].pm25 == 30.0

    def test_long_gap_is_left_as_is(self):
        cleaned, filled = interpolate_gaps(series([10.0, None, None, None, None, 40.0]))
        assert filled == 0
        assert cleaned[2].pm25 is None

    def test_edge_gap_is_not_extrapolated(self):
        cleaned, filled = interpolate_gaps(series([None, 10.0, 20.0, None]))
        assert filled == 0
        assert cleaned[0].pm25 is None
        assert cleaned[-1].pm25 is None


class TestPipeline:
    def test_full_pipeline_reports_every_stage(self):
        values: list[float | None] = [20.0] * 30
        values[10] = -1.0     # вне физического диапазона
        values[20] = 900.0    # выброс
        values[25] = None     # короткий пропуск
        records = series(values)
        records.append(records[-1])  # дубликат последней метки времени

        cleaned, report = clean_air_quality(records)

        assert report.total_in == 31
        assert report.duplicates_removed == 1
        assert report.out_of_range == 1
        assert report.outliers_removed == 1
        assert report.gaps_filled >= 1
        assert report.total_out == 30
        assert len(cleaned) == 30
