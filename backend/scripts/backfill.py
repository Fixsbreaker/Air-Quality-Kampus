"""Выкачка исторического архива.

    python -m scripts.backfill --days 730

Без исторических данных ML-модель обучить нельзя, поэтому скрипт
запускается один раз сразу после первого поднятия базы.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from app.config import settings
from app.db import session_scope
from app.ingestion.pipeline import backfill

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
)
logger = logging.getLogger("backfill")


def main() -> int:
    parser = argparse.ArgumentParser(description="Загрузка исторического архива Open-Meteo")
    parser.add_argument(
        "--days",
        type=int,
        default=settings.train_history_days,
        help="глубина архива в днях (по умолчанию из TRAIN_HISTORY_DAYS)",
    )
    args = parser.parse_args()

    started = time.monotonic()
    logger.info("Загружаю архив за %s дней. Это займёт несколько минут.", args.days)

    try:
        with session_scope() as db:
            results = backfill(db, days=args.days)
    except Exception:  # noqa: BLE001
        logger.exception("Backfill прерван")
        return 1

    for result in results:
        logger.info(
            "%-14s наблюдений +%s, погоды +%s",
            result.location,
            result.measurements.get("inserted", 0),
            result.weather.get("inserted", 0),
        )

    logger.info("Готово за %.1f с", time.monotonic() - started)
    return 0


if __name__ == "__main__":
    sys.exit(main())
