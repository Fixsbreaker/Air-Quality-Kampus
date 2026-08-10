"""Точка входа FastAPI-приложения."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import api_router
from app.config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

DESCRIPTION = """
Сервис мониторинга и прогноза качества воздуха на кампусе КБТУ.

Отвечает на два практических вопроса:
* можно ли сегодня проводить занятия спортом на улице;
* можно ли открывать окна в аудиториях.

Данные собираются ежечасно из Open-Meteo Air Quality API, индекс AQI
считается по методике US EPA, прогноз на 48 часов строит градиентный
бустинг, обученный на двухлетнем архиве.
"""

TAGS_METADATA = [
    {"name": "Качество воздуха", "description": "Текущие значения и история наблюдений"},
    {"name": "Прогноз", "description": "Прогноз PM2.5 и AQI на ближайшие сутки-двое"},
    {"name": "Подписки", "description": "Управление подписками Telegram-бота"},
    {"name": "Администрирование", "description": "Выгрузка отчётов и метрики моделей"},
    {"name": "Служебное", "description": "Справочники и healthcheck"},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Запуск API, окружение=%s, версия=%s", settings.app_env, __version__)
    yield
    logger.info("Остановка API")


app = FastAPI(
    title="KBTU Air Quality Kampus API",
    description=DESCRIPTION,
    version=__version__,
    openapi_tags=TAGS_METADATA,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    contact={"name": "Команда проекта", "url": "https://kbtu.edu.kz"},
    license_info={"name": "MIT"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Ошибки доменной логики отдаём как 400, а не как 500."""
    logger.warning("ValueError на %s: %s", request.url.path, exc)
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "service": "KBTU Air Quality Kampus",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
    }
