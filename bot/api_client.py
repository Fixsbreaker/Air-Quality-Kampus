"""HTTP-клиент к backend API.

Бот не ходит в базу напрямую: вся логика (расчёт AQI, рекомендации,
прогноз) живёт в API, а бот остаётся тонким слоем представления. Так
одни и те же правила работают и в дашборде, и в мессенджере.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ApiError(RuntimeError):
    """API недоступен или вернул ошибку."""


class ApiClient:
    def __init__(self, base_url: str, admin_token: str = "", timeout: float = 15.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._admin_token = admin_token
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._base_url}{path}"
        try:
            response = await self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise ApiError(f"Сервис недоступен: {exc}") from exc

        if response.status_code == 404:
            raise ApiError(response.json().get("detail", "Данные не найдены"))
        if response.status_code >= 400:
            raise ApiError(f"Ошибка сервиса ({response.status_code})")

        return response.json()

    async def current(self, location: str = "main") -> dict:
        return await self._request("GET", "/api/current", params={"location": location})

    async def forecast(self, location: str = "main", hours: int = 48) -> dict:
        return await self._request(
            "GET", "/api/forecast", params={"location": location, "hours": hours}
        )

    async def locations(self) -> list[dict]:
        return await self._request("GET", "/api/locations")

    async def subscribe(self, tg_id: int, threshold: int, location: str) -> dict:
        return await self._request(
            "POST",
            "/api/subscribe",
            json={"tg_id": tg_id, "threshold_aqi": threshold, "location": location},
        )

    async def unsubscribe(self, tg_id: int) -> dict:
        return await self._request("POST", "/api/unsubscribe", params={"tg_id": tg_id})

    async def subscribers(self) -> list[dict]:
        return await self._request(
            "GET", "/api/subscribers", headers={"X-Admin-Token": self._admin_token}
        )
