"""Тесты таблицы рекомендаций из технического задания."""

from __future__ import annotations

import pytest

from app.services.recommendations import recommend, short_summary


@pytest.mark.parametrize(
    ("aqi", "category", "text"),
    [
        (25, "Хорошо", "Занятия на улице без ограничений"),
        (50, "Хорошо", "Занятия на улице без ограничений"),
        (51, "Умеренно", "Норма; чувствительным людям — сократить нагрузку"),
        (100, "Умеренно", "Норма; чувствительным людям — сократить нагрузку"),
        (101, "Вредно для чувствительных", "Физкультуру перенести в зал; астматикам — маска"),
        (150, "Вредно для чувствительных", "Физкультуру перенести в зал; астматикам — маска"),
        (151, "Вредно", "Отменить занятия на улице, закрыть окна, включить рециркуляцию"),
        (200, "Вредно", "Отменить занятия на улице, закрыть окна, включить рециркуляцию"),
        (250, "Очень вредно", "Минимизировать выход на улицу"),
    ],
)
def test_matches_tz_table(aqi, category, text):
    rec = recommend(aqi)
    assert rec.category == category
    assert rec.text == text


class TestActionFlags:
    def test_sport_allowed_up_to_100(self):
        assert recommend(100).outdoor_sport is True
        assert recommend(101).outdoor_sport is False

    def test_windows_closed_from_151(self):
        assert recommend(150).open_windows is True
        assert recommend(151).open_windows is False

    def test_mask_advised_from_101(self):
        assert recommend(100).mask_advised is False
        assert recommend(101).mask_advised is True

    def test_extreme_values_are_handled(self):
        rec = recommend(500)
        assert rec.outdoor_sport is False
        assert rec.open_windows is False
        assert rec.mask_advised is True


def test_color_changes_between_categories():
    colors = {recommend(value).color for value in (25, 75, 125, 175, 250)}
    assert len(colors) == 5


def test_short_summary_format():
    assert short_summary(87) == "AQI 87 — Умеренно. Норма; чувствительным людям — сократить нагрузку."
