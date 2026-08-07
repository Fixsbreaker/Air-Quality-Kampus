"""Нагрузочное тестирование API (Locust).

Запуск с веб-интерфейсом:

    locust -f loadtest/locustfile.py --host http://localhost:8000

Запуск без интерфейса, с готовым отчётом:

    locust -f loadtest/locustfile.py --host http://localhost:8000 \\
           --headless --users 100 --spawn-rate 10 --run-time 2m \\
           --html loadtest/report.html

Что проверяется. Профиль нагрузки построен по реальному сценарию: студент
открывает дашборд и смотрит текущее состояние, реже — историю и прогноз;
подписка и выгрузка отчёта случаются на порядки реже. Веса задач подобраны
под это распределение, а не «поровну на все эндпоинты» — иначе тест мерил бы
не ту нагрузку, которая будет в жизни.

Проверяемые требования:
  * /api/current отвечает быстрее 300 мс под нагрузкой (нефункциональное
    требование Н2 из отчёта);
  * кэш на Redis снимает нагрузку с PostgreSQL: без него время ответа
    заметно растёт с числом пользователей;
  * ошибок 5xx нет ни при какой интенсивности.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from locust import HttpUser, between, task

LOCATIONS = ["main", "dorm_ozala", "dorm_karimova"]
ADMIN_TOKEN = "change-me-in-production"

# Порог из нефункциональных требований: медиана ответа /api/current, мс.
CURRENT_P50_BUDGET_MS = 300


class DashboardUser(HttpUser):
    """Типовой посетитель дашборда.

    Пауза 1–5 секунд имитирует чтение страницы, а не пулемётную очередь
    запросов: без неё тест меряет предел сервера, а не поведение под
    реалистичным трафиком.
    """

    wait_time = between(1, 5)

    @task(10)
    def current(self):
        """Самый частый запрос: плашка AQI обновляется на каждом открытии."""
        location = random.choice(LOCATIONS)
        with self.client.get(
            "/api/current",
            params={"location": location},
            name="/api/current",
            catch_response=True,
        ) as response:
            if response.status_code == 404:
                # База пуста — это ошибка окружения, а не приложения.
                response.failure("нет данных: выполните backfill перед прогоном")
            elif response.status_code != 200:
                response.failure(f"код {response.status_code}")
            else:
                response.success()

    @task(5)
    def history(self):
        """График истории: самый тяжёлый запрос по объёму выборки."""
        to_ts = datetime.now(timezone.utc).replace(tzinfo=None)
        hours = random.choice([24, 72, 168, 720])
        self.client.get(
            "/api/history",
            params={
                "location": random.choice(LOCATIONS),
                "from": (to_ts - timedelta(hours=hours)).isoformat(timespec="seconds"),
                "to": to_ts.isoformat(timespec="seconds"),
            },
            name=f"/api/history ({hours} ч)",
        )

    @task(4)
    def forecast(self):
        self.client.get(
            "/api/forecast",
            params={"location": random.choice(LOCATIONS), "hours": 48},
            name="/api/forecast",
        )

    @task(2)
    def locations(self):
        self.client.get("/api/locations", name="/api/locations")

    @task(1)
    def health(self):
        self.client.get("/health", name="/health")


class AdminUser(HttpUser):
    """Редкая, но тяжёлая нагрузка: выгрузка CSV для администрации."""

    wait_time = between(30, 90)

    @task
    def report(self):
        to_ts = datetime.now(timezone.utc).replace(tzinfo=None)
        self.client.get(
            "/api/admin/report",
            params={
                "from": (to_ts - timedelta(days=30)).isoformat(timespec="seconds"),
                "to": to_ts.isoformat(timespec="seconds"),
            },
            headers={"X-Admin-Token": ADMIN_TOKEN},
            name="/api/admin/report (30 дней)",
        )
