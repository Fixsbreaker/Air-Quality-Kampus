"""Фоновый процесс: планировщик задач сбора данных, прогноза и обучения.

Запуск: python -m app.worker
В Docker Compose поднимается отдельным сервисом `worker`.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.scheduler import build_scheduler, job_forecast, job_ingest

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
)
logger = logging.getLogger("worker")


def main() -> None:
    logger.info("Старт воркера, часовой пояс расписания: %s", settings.tz)

    # Первый прогон сразу после старта, чтобы не ждать до следующего часа.
    job_ingest()
    job_forecast()

    scheduler = build_scheduler()
    for job in scheduler.get_jobs():
        logger.info("Задача '%s' (%s): %s", job.name, job.id, job.trigger)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановка воркера")


if __name__ == "__main__":
    main()
