"""Тесты расчёта AQI по методике US EPA."""

from __future__ import annotations

import pytest

from app.services import aqi as aqi_module
from app.services.aqi import (
    aqi_from_pm10,
    aqi_from_pm25,
    category_of,
    compute_aqi,
    truncate,
)


class TestTruncate:
    def test_truncates_not_rounds(self):
        # 12.99 -> 12.9, а не 13.0: EPA требует именно усечения
        assert truncate(12.99, 1) == 12.9
        assert truncate(54.9, 0) == 54.0

    def test_zero_and_negative(self):
        assert truncate(0.0, 1) == 0.0
        assert truncate(-3.7, 0) == -3.0


class TestPm25:
    @pytest.mark.parametrize(
        ("concentration", "expected"),
        [
            (0.0, 0),      # нижняя граница шкалы
            (9.0, 50),     # верх «хорошо» в редакции 2024
            (9.1, 51),     # первая точка «умеренно»
            (35.4, 100),   # верх «умеренно»
            (35.5, 101),   # «вредно для чувствительных»
            (55.4, 150),
            (55.5, 151),   # «вредно»
            (125.4, 200),
            (125.5, 201),  # «очень вредно»
        ],
    )
    def test_breakpoint_edges_2024(self, concentration, expected):
        assert aqi_from_pm25(concentration) == expected

    def test_linear_interpolation_inside_segment(self):
        # Середина сегмента 9.1–35.4 -> примерно середина 51–100
        assert aqi_from_pm25(22.2) == pytest.approx(75, abs=1)

    def test_above_scale_is_capped(self):
        assert aqi_from_pm25(5000) == 500

    def test_none_and_negative(self):
        assert aqi_from_pm25(None) is None
        assert aqi_from_pm25(-1) is None

    def test_legacy_2012_table(self, monkeypatch):
        monkeypatch.setattr(aqi_module.settings, "aqi_breakpoints", "epa_2012")
        # В редакции 2012 порог «хорошо» был 12.0 вместо 9.0
        assert aqi_from_pm25(12.0) == 50
        assert aqi_from_pm25(9.0) < 50


class TestPm10:
    @pytest.mark.parametrize(
        ("concentration", "expected"),
        [(0, 0), (54, 50), (55, 51), (154, 100), (155, 101), (254, 150), (354, 200)],
    )
    def test_breakpoint_edges(self, concentration, expected):
        assert aqi_from_pm10(concentration) == expected

    def test_none(self):
        assert aqi_from_pm10(None) is None


class TestCategories:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (0, "Хорошо"),
            (50, "Хорошо"),
            (51, "Умеренно"),
            (100, "Умеренно"),
            (101, "Вредно для чувствительных"),
            (150, "Вредно для чувствительных"),
            (151, "Вредно"),
            (200, "Вредно"),
            (201, "Очень вредно"),
            (400, "Очень вредно"),
        ],
    )
    def test_boundaries_match_tz(self, value, expected):
        assert category_of(value) == expected


class TestCompute:
    def test_takes_maximum_of_subindices(self):
        # PM10 = 200 мкг/м³ даёт больший индекс, чем PM2.5 = 10
        result = compute_aqi(pm25=10.0, pm10=200.0)
        assert result is not None
        assert result.dominant_pollutant == "pm10"
        assert result.aqi == result.pm10_aqi

    def test_pm25_can_dominate(self):
        result = compute_aqi(pm25=150.0, pm10=20.0)
        assert result.dominant_pollutant == "pm25"

    def test_single_pollutant_available(self):
        result = compute_aqi(pm25=30.0, pm10=None)
        assert result is not None
        assert result.pm10_aqi is None
        assert result.dominant_pollutant == "pm25"

    def test_no_data_returns_none(self):
        assert compute_aqi(None, None) is None
