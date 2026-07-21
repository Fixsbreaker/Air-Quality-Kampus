"""Очистка часового ряда: дубликаты, физически невозможные значения,
статистические выбросы и короткие пропуски.

Порядок операций важен и выбран так:
  1. дубликаты   — иначе одна и та же метка времени попадёт в ряд дважды;
  2. границы     — отрицательные и абсурдные значения выбрасываются сразу,
                   чтобы не портить оценку медианы и разброса;
  3. выбросы     — скользящая медиана + MAD, устойчивы к одиночным пикам;
  4. пропуски    — линейная интерполяция, но только коротких провалов.

Длинные провалы намеренно не заполняются: восстановленные «из воздуха»
сутки исказят обучение модели сильнее, чем честный пропуск.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, replace
from datetime import timedelta

from app.ingestion.openmeteo import AirQualityRecord

logger = logging.getLogger(__name__)

# Физически допустимые диапазоны концентраций, мкг/м³
PHYSICAL_LIMITS: dict[str, tuple[float, float]] = {
    "pm25": (0.0, 1000.0),
    "pm10": (0.0, 2000.0),
    "no2": (0.0, 1000.0),
    "o3": (0.0, 1000.0),
}

FIELDS = tuple(PHYSICAL_LIMITS)

MAD_WINDOW = 24          # окно скользящей медианы, часов
MAD_THRESHOLD = 6.0      # во сколько MAD значение считается выбросом
MAD_SCALE = 1.4826       # приведение MAD к масштабу стандартного отклонения
MAX_GAP_HOURS = 3        # максимальная длина интерполируемого пропуска


@dataclass
class CleaningReport:
    total_in: int = 0
    duplicates_removed: int = 0
    out_of_range: int = 0
    outliers_removed: int = 0
    gaps_filled: int = 0
    total_out: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "total_in": self.total_in,
            "duplicates_removed": self.duplicates_removed,
            "out_of_range": self.out_of_range,
            "outliers_removed": self.outliers_removed,
            "gaps_filled": self.gaps_filled,
            "total_out": self.total_out,
        }


def drop_duplicates(records: list[AirQualityRecord]) -> tuple[list[AirQualityRecord], int]:
    """Оставить по одной записи на метку времени (побеждает последняя)."""
    by_ts: dict[object, AirQualityRecord] = {}
    for record in records:
        by_ts[record.ts] = record
    unique = sorted(by_ts.values(), key=lambda item: item.ts)
    return unique, len(records) - len(unique)


def enforce_physical_limits(
    records: list[AirQualityRecord],
) -> tuple[list[AirQualityRecord], int]:
    """Заменить на None значения вне физически возможного диапазона."""
    removed = 0
    cleaned: list[AirQualityRecord] = []

    for record in records:
        patch: dict[str, float | None] = {}
        for field in FIELDS:
            value = getattr(record, field)
            if value is None:
                continue
            low, high = PHYSICAL_LIMITS[field]
            if not (low <= value <= high):
                patch[field] = None
                removed += 1
        cleaned.append(replace(record, **patch) if patch else record)

    return cleaned, removed


def _mad_outlier_flags(values: list[float | None]) -> list[bool]:
    """Пометить выбросы по скользящей медиане и MAD."""
    flags = [False] * len(values)

    for i, value in enumerate(values):
        if value is None:
            continue
        start = max(0, i - MAD_WINDOW // 2)
        window = [v for v in values[start : i + MAD_WINDOW // 2 + 1] if v is not None]
        if len(window) < 8:
            continue

        median = statistics.median(window)
        deviations = [abs(v - median) for v in window]
        mad = statistics.median(deviations)

        if mad == 0:
            # Окно практически константное — MAD вырождается в ноль и делить
            # на него нельзя. Аномалией считаем отклонение, сопоставимое с
            # самим уровнем сигнала.
            if abs(value - median) > max(1.0, abs(median)):
                flags[i] = True
            continue

        if abs(value - median) / (MAD_SCALE * mad) > MAD_THRESHOLD:
            flags[i] = True

    return flags


def remove_outliers(records: list[AirQualityRecord]) -> tuple[list[AirQualityRecord], int]:
    """Убрать одиночные аномальные пики по каждому загрязнителю отдельно."""
    if not records:
        return records, 0

    removed = 0
    patched: list[dict[str, float | None]] = [{} for _ in records]

    for field in FIELDS:
        column = [getattr(record, field) for record in records]
        for i, is_outlier in enumerate(_mad_outlier_flags(column)):
            if is_outlier:
                patched[i][field] = None
                removed += 1

    cleaned = [
        replace(record, **patch) if patch else record
        for record, patch in zip(records, patched, strict=True)
    ]
    return cleaned, removed


def interpolate_gaps(
    records: list[AirQualityRecord], max_gap_hours: int = MAX_GAP_HOURS
) -> tuple[list[AirQualityRecord], int]:
    """Линейно заполнить пропуски длиной не более max_gap_hours."""
    if not records:
        return records, 0

    filled = 0
    values: dict[str, list[float | None]] = {
        field: [getattr(record, field) for record in records] for field in FIELDS
    }

    for column in values.values():
        i = 0
        while i < len(column):
            if column[i] is not None:
                i += 1
                continue

            gap_start = i
            while i < len(column) and column[i] is None:
                i += 1
            gap_end = i  # первый индекс после пропуска

            left = gap_start - 1
            if left < 0 or gap_end >= len(column):
                continue  # пропуск на краю ряда — экстраполировать не будем

            gap_len = gap_end - gap_start
            if gap_len > max_gap_hours:
                continue

            # Интерполируем только если соседние точки идут подряд по времени.
            expected = timedelta(hours=gap_len + 1)
            if records[gap_end].ts - records[left].ts != expected:
                continue

            start_value = column[left]
            end_value = column[gap_end]
            if start_value is None or end_value is None:
                continue

            step = (end_value - start_value) / (gap_len + 1)
            for offset in range(1, gap_len + 1):
                column[gap_start + offset - 1] = round(start_value + step * offset, 3)
                filled += 1

    cleaned = [
        replace(record, **{field: values[field][i] for field in FIELDS})
        for i, record in enumerate(records)
    ]
    return cleaned, filled


def clean_air_quality(
    records: list[AirQualityRecord],
) -> tuple[list[AirQualityRecord], CleaningReport]:
    """Полный конвейер очистки. Возвращает ряд и отчёт для логов/дневника."""
    report = CleaningReport(total_in=len(records))

    records, report.duplicates_removed = drop_duplicates(records)
    records, report.out_of_range = enforce_physical_limits(records)
    records, report.outliers_removed = remove_outliers(records)
    records, report.gaps_filled = interpolate_gaps(records)

    report.total_out = len(records)
    logger.info("Очистка данных: %s", report.as_dict())
    return records, report
