"""Маршруты HTTP API."""

from fastapi import APIRouter

from app.api import admin, current, forecast, history, meta, subscribe

api_router = APIRouter()
api_router.include_router(meta.router)
api_router.include_router(current.router)
api_router.include_router(history.router)
api_router.include_router(forecast.router)
api_router.include_router(subscribe.router)
api_router.include_router(admin.router)

__all__ = ["api_router"]
