"""Разовый запуск часового парсера: python -m scripts.ingest_once"""

from __future__ import annotations

import json
import logging
import sys

from app.db import session_scope
from app.ingestion.pipeline import ingest_once

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
)
logger = logging.getLogger("ingest")


def main() -> int:
    try:
        with session_scope() as db:
            results = ingest_once(db)
    except Exception:  # noqa: BLE001
        logger.exception("Сбор данных прерван")
        return 1

    print(json.dumps([item.as_dict() for item in results], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
