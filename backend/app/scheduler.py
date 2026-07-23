"""Расписание фоновых задач (APScheduler).

Три регулярные задачи:
  * сбор данных    — каждый час на INGEST_CRON_MINUTE-й минуте;
  * прогноз        — каждый час на FORECAST_CRON_MINUTE-й минуте (после сбора);
  * переобучение   — раз в сутки в RETRAIN_CRON_HOUR.

Задачи запускаются в отдельном процессе (app/worker.py), а не внутри
веб-приложения: иначе при нескольких воркерах uvicorn один и тот же job
выполнялся бы параллельно несколько раз.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.db import session_scope
from app.ingestion.pipeline import ingest_once
from app.ml.predict import refresh_all
from app.ml.train import train

logger = logging.getLogger(__name__)


def job_ingest() -> None:
    """Часовой сбор данных из Open-Meteo."""
    try:
        with session_scope() as db:
            results = ingest_once(db)
        logger.info("Сбор данных: %s", [item.as_dict() for item in results])
    except Exception:  # noqa: BLE001 - падение задачи не должно ронять планировщик
        logger.exception("Задача сбора данных завершилась ошибкой")


def job_forecast() -> None:
    """Пересчёт прогноза на 48 часов активной моделью."""
    try:
        with session_scope() as db:
            written = refresh_all(db)
        logger.info("Прогноз обновлён: %s", written)
    except FileNotFoundError as exc:
        logger.warning("Прогноз пропущен: %s", exc)
    except Exception:  # noqa: BLE001
        logger.exception("Задача прогноза завершилась ошибкой")


def job_retrain() -> None:
    """Ночное переобучение модели на накопленных данных."""
    try:
        with session_scope() as db:
            report = train(db)
        logger.info(
            "Переобучение завершено: версия=%s MAE=%.3f (baseline %.3f, улучшение %.2f%%)",
            report.version,
            report.cv_metrics["mae"],
            report.baseline_metrics[report.best_baseline_name]["mae"],
            report.improvement_pct,
        )
    except ValueError as exc:
        logger.warning("Переобучение пропущено: %s", exc)
    except Exception:  # noqa: BLE001
        logger.exception("Задача переобучения завершилась ошибкой")


def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=settings.tz)

    scheduler.add_job(
        job_ingest,
        CronTrigger(minute=settings.ingest_cron_minute),
        id="ingest",
        name="Сбор данных Open-Meteo",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=600,
    )
    scheduler.add_job(
        job_forecast,
        CronTrigger(minute=settings.forecast_cron_minute),
        id="forecast",
        name="Пересчёт прогноза",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=600,
    )
    scheduler.add_job(
        job_retrain,
        CronTrigger(hour=settings.retrain_cron_hour, minute=0),
        id="retrain",
        name="Переобучение модели",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    return scheduler
