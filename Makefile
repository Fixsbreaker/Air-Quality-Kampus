.DEFAULT_GOAL := help
COMPOSE := docker compose

help: ## Показать список команд
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

init: ## Создать .env из шаблона
	@test -f .env || cp .env.example .env && echo ".env готов"

up: ## Поднять db + redis + api + frontend
	$(COMPOSE) up -d --build aqi-db aqi-redis aqi-api aqi-web

up-all: ## Поднять всё, включая worker и бота
	$(COMPOSE) --profile bot up -d --build

down: ## Остановить всё
	$(COMPOSE) down

logs: ## Логи api и worker
	$(COMPOSE) logs -f aqi-api aqi-worker

migrate: ## Применить миграции
	$(COMPOSE) exec aqi-api alembic upgrade head

revision: ## Новая миграция: make revision M="описание"
	$(COMPOSE) exec aqi-api alembic revision -m "$(M)"

backfill: ## Выкачать исторический архив: make backfill DAYS=730
	$(COMPOSE) exec aqi-api python -m scripts.backfill --days $(or $(DAYS),730)

ingest: ## Разовый запуск часового парсера
	$(COMPOSE) exec aqi-api python -m scripts.ingest_once

train: ## Обучить модель и записать метрики
	$(COMPOSE) exec aqi-api python -m scripts.train

forecast: ## Пересчитать прогноз на 48 часов
	$(COMPOSE) exec aqi-api python -m scripts.make_forecast

test: ## Запустить тесты
	cd backend && pytest -q

test-cov: ## Тесты с покрытием
	cd backend && pytest --cov=app --cov-report=term-missing

loadtest: ## Нагрузочный тест (нужен поднятый стек и наполненная база)
	cd backend && .venv/bin/locust -f ../loadtest/locustfile.py --host http://localhost:8000 \
		--headless --users $(or $(USERS),100) --spawn-rate 10 --run-time $(or $(TIME),2m) \
		--html ../loadtest/report.html

redis-cli: ## Консоль Redis
	$(COMPOSE) exec aqi-redis redis-cli

lint: ## Проверка стиля
	cd backend && ruff check app tests scripts

fmt: ## Автоформатирование
	cd backend && ruff format app tests scripts

psql: ## Консоль PostgreSQL
	$(COMPOSE) exec aqi-db psql -U $${POSTGRES_USER:-aqi} -d $${POSTGRES_DB:-aqi}

.PHONY: help init up up-all down logs migrate revision backfill ingest train forecast test test-cov loadtest redis-cli lint fmt psql
