"""Обучение модели: python -m scripts.train [--days 730] [--horizon 48]

Скрипт печатает таблицу сравнения с baseline — именно эти цифры идут
в отчёт по практике.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from app.config import settings
from app.db import session_scope
from app.ml.train import train

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
)
logger = logging.getLogger("train")


def main() -> int:
    parser = argparse.ArgumentParser(description="Обучение модели прогноза PM2.5")
    parser.add_argument("--days", type=int, default=settings.train_history_days)
    parser.add_argument("--horizon", type=int, default=settings.forecast_horizon_hours)
    parser.add_argument("--splits", type=int, default=4, help="число фолдов кросс-валидации")
    parser.add_argument(
        "--no-activate",
        action="store_true",
        help="обучить и сохранить, но не делать модель активной",
    )
    args = parser.parse_args()

    try:
        with session_scope() as db:
            report = train(
                db,
                horizon=args.horizon,
                days=args.days,
                n_splits=args.splits,
                activate=not args.no_activate,
            )
    except ValueError as exc:
        logger.error("%s", exc)
        return 2
    except Exception:  # noqa: BLE001
        logger.exception("Обучение прервано")
        return 1

    baseline = report.baseline_metrics[report.best_baseline_name]
    print()
    print(f"Версия модели      : {report.version}")
    print(f"Алгоритм           : {report.algorithm}")
    print(f"Строк в выборке    : {report.rows_used}")
    print(f"MAE модели         : {report.cv_metrics['mae']:.3f} мкг/м³")
    print(f"RMSE модели        : {report.cv_metrics['rmse']:.3f} мкг/м³")
    print(f"Лучший baseline    : {report.best_baseline_name} (MAE {baseline['mae']:.3f})")
    print(f"Улучшение          : {report.improvement_pct:+.2f} %")
    print(f"Лучше baseline     : {'да' if report.beats_baseline else 'НЕТ'}")
    print()

    print("Ошибка по горизонтам (последний фолд):")
    print(f"{'ч':>4} {'MAE модели':>12} {'MAE baseline':>14} {'выигрыш, %':>12}")
    for row in report.by_horizon:
        if int(row["horizon"]) % 6 == 0 or int(row["horizon"]) == 1:
            print(
                f"{int(row['horizon']):>4} {row['mae_model']:>12.3f} "
                f"{row['mae_baseline']:>14.3f} {row['improvement_pct']:>12.2f}"
            )

    with open("models/last_train_report.json", "w", encoding="utf-8") as handle:
        json.dump(report.as_dict(), handle, ensure_ascii=False, indent=2, default=str)
    print("\nПодробный отчёт: models/last_train_report.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
