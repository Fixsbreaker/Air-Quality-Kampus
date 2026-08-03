"""Пересчёт прогноза на 48 часов: python -m scripts.make_forecast"""

from __future__ import annotations

import logging
import sys

from app.db import session_scope
from app.ml.predict import refresh_all

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
)
logger = logging.getLogger("forecast")


def main() -> int:
    try:
        with session_scope() as db:
            written = refresh_all(db)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 2
    except Exception:  # noqa: BLE001
        logger.exception("Расчёт прогноза прерван")
        return 1

    for location, count in written.items():
        print(f"{location:<14} записано точек прогноза: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
