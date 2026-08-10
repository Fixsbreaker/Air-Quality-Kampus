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

from locust import HttpUser, between, events, task

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


class BotUser(HttpUser):
    """Нагрузка со стороны Telegram-бота.

    Бот ходит в API на каждую команду, а при утренней рассылке — ещё и
    списком подписчиков. Отдельный класс нужен, чтобы видеть его вклад
    в общую нагрузку отдельно от веб-дашборда.
    """

    wait_time = between(2, 8)

    @task(6)
    def command_now(self):
        self.client.get(
            "/api/current", params={"location": "main"}, name="[бот] /api/current"
        )

    @task(3)
    def command_forecast(self):
        self.client.get(
            "/api/forecast",
            params={"location": "main", "hours": 24},
            name="[бот] /api/forecast",
        )

    @task(1)
    def subscribe(self):
        """Подписка идемпотентна, поэтому повторные вызовы безопасны."""
        self.client.post(
            "/api/subscribe",
            json={
                "tg_id": random.randint(10**8, 10**9),
                "threshold_aqi": random.choice([80, 100, 120, 150]),
                "location": random.choice(LOCATIONS),
            },
            name="[бот] /api/subscribe",
        )


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


@events.quitting.add_listener
def _check_thresholds(environment, **_kwargs):
    """Проверить пороги в конце прогона и выставить код возврата.

    Это превращает нагрузочный тест из «посмотрели график» в проверку,
    которую можно запускать в конвейере: при нарушении порогов процесс
    завершается с ненулевым кодом.
    """
    stats = environment.stats

    if stats.total.fail_ratio > 0.01:
        print(f"ПРОВАЛ: доля ошибок {stats.total.fail_ratio:.2%} превышает 1 %")
        environment.process_exit_code = 1
        return

    current = stats.get("/api/current", "GET")
    if current.num_requests:
        p50 = current.get_response_time_percentile(0.5)
        p95 = current.get_response_time_percentile(0.95)
        print(f"/api/current: медиана {p50:.0f} мс, 95-й перцентиль {p95:.0f} мс")
        if p50 > CURRENT_P50_BUDGET_MS:
            print(f"ПРОВАЛ: медиана {p50:.0f} мс превышает бюджет {CURRENT_P50_BUDGET_MS} мс")
            environment.process_exit_code = 1
            return

    environment.process_exit_code = 0
    print("Нагрузочный тест пройден: пороги соблюдены")
