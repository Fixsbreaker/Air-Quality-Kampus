"""Общие зависимости FastAPI: локация, админский токен, перевод времени."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Header, HTTPException, Query, status

from app.config import settings
from app.locations import CampusLocation, get_location

ALMATY_OFFSET = timedelta(hours=5)  # Asia/Almaty, UTC+5 без перехода на летнее время


def location_dep(
    location: Annotated[
        str, Query(description="Код объекта: main, dorm_ozala, dorm_karimova")
    ] = "main",
) -> CampusLocation:
    try:
        return get_location(location)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def require_admin(
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> None:
    """Простейшая защита админских эндпоинтов заголовком с общим секретом.

    Для учебного проекта этого достаточно; в проде на это место ставится
    OAuth2/JWT или проверка на стороне реверс-прокси.
    """
    if not x_admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Требуется корректный заголовок X-Admin-Token",
        )


def to_local(value: datetime) -> datetime:
    """UTC (naive) → местное время Алматы (naive)."""
    return value + ALMATY_OFFSET


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
