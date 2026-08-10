"""Клиент Open-Meteo — основной источник данных проекта.

API бесплатный и не требует ключа. Используются три эндпоинта:

  * air-quality        — PM2.5/PM10/NO2/O3, прошлое + прогноз до 7 суток;
  * forecast (weather) — погода, прошлое + прогноз;
  * archive (weather)  — исторический архив погоды глубиной в годы.

Все запросы делаются с timezone=UTC, чтобы в базу попадало единое время
без сдвигов при переходе на летнее время (см. docstring в app/models.py).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

AQ_VARIABLES = ["pm2_5", "pm10", "nitrogen_dioxide", "ozone"]
WEATHER_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "wind_direction_10m",
    "surface_pressure",
]


@dataclass(frozen=True)
class AirQualityRecord:
    ts: datetime
    pm25: float | None
    pm10: float | None
    no2: float | None
    o3: float | None


@dataclass(frozen=True)
class WeatherRecord:
    ts: datetime
    temp: float | None
    humidity: float | None
    wind_speed: float | None
    wind_dir: float | None
    pressure: float | None


class OpenMeteoError(RuntimeError):
    """Источник вернул ошибку или неожиданный формат ответа."""


def _parse_ts(raw: str) -> datetime:
    """'2026-08-07T13:00' -> datetime(2026, 8, 7, 13, 0) в UTC (naive)."""
    return datetime.fromisoformat(raw)


def _column(hourly: dict, name: str) -> list:
    values = hourly.get(name)
    if values is None:
        return [None] * len(hourly.get("time", []))
    return values


class OpenMeteoClient:
    """Тонкая обёртка над httpx с ретраями и единым разбором ответа."""

    def __init__(self, client: httpx.Client | None = None, retries: int = 3) -> None:
        self._client = client or httpx.Client(timeout=settings.http_timeout_seconds)
        self._owns_client = client is None
        self._retries = retries

    def __enter__(self) -> OpenMeteoClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # ------------------------------------------------------------------ HTTP

    def _get(self, url: str, params: dict) -> dict:
        last_error: Exception | None = None
        for attempt in range(1, self._retries + 1):
            try:
                response = self._client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                logger.warning("Open-Meteo: попытка %s/%s не удалась: %s", attempt, self._retries, exc)
                continue

            if "error" in payload and payload.get("error"):
                raise OpenMeteoError(payload.get("reason", "неизвестная ошибка API"))
            if "hourly" not in payload:
                raise OpenMeteoError(f"В ответе нет секции 'hourly': {list(payload)}")
            return payload

        raise OpenMeteoError(f"Не удалось получить данные с {url}: {last_error}")

    # ------------------------------------------------------- качество воздуха

    def fetch_air_quality(
        self,
        lat: float,
        lon: float,
        *,
        past_days: int | None = 2,
        forecast_days: int | None = 2,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[AirQualityRecord]:
        params: dict[str, object] = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(AQ_VARIABLES),
            "timezone": "UTC",
        }
        if start_date and end_date:
            params["start_date"] = start_date.isoformat()
            params["end_date"] = end_date.isoformat()
        else:
            if past_days is not None:
                params["past_days"] = past_days
            if forecast_days is not None:
                params["forecast_days"] = forecast_days

        hourly = self._get(settings.open_meteo_aq_url, params)["hourly"]
        times = hourly.get("time", [])
        pm25 = _column(hourly, "pm2_5")
        pm10 = _column(hourly, "pm10")
        no2 = _column(hourly, "nitrogen_dioxide")
        o3 = _column(hourly, "ozone")

        return [
            AirQualityRecord(
                ts=_parse_ts(times[i]),
                pm25=pm25[i],
                pm10=pm10[i],
                no2=no2[i],
                o3=o3[i],
            )
            for i in range(len(times))
        ]

    # ------------------------------------------------------------------ погода

    def fetch_weather(
        self,
        lat: float,
        lon: float,
        *,
        past_days: int | None = 2,
        forecast_days: int | None = 2,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[WeatherRecord]:
        """Погода из forecast-эндпоинта (прошлое до 92 дней + прогноз)."""
        params: dict[str, object] = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(WEATHER_VARIABLES),
            "timezone": "UTC",
        }
        if start_date and end_date:
            params["start_date"] = start_date.isoformat()
            params["end_date"] = end_date.isoformat()
        else:
            if past_days is not None:
                params["past_days"] = past_days
            if forecast_days is not None:
                params["forecast_days"] = forecast_days

        return self._parse_weather(self._get(settings.open_meteo_weather_url, params))

    def fetch_weather_archive(
        self, lat: float, lon: float, start_date: date, end_date: date
    ) -> list[WeatherRecord]:
        """Погода из архивного эндпоинта — для глубокого backfill."""
        params: dict[str, object] = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(WEATHER_VARIABLES),
            "timezone": "UTC",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        return self._parse_weather(self._get(settings.open_meteo_weather_archive_url, params))

    @staticmethod
    def _parse_weather(payload: dict) -> list[WeatherRecord]:
        hourly = payload["hourly"]
        times = hourly.get("time", [])
        temp = _column(hourly, "temperature_2m")
        humidity = _column(hourly, "relative_humidity_2m")
        wind_speed = _column(hourly, "wind_speed_10m")
        wind_dir = _column(hourly, "wind_direction_10m")
        pressure = _column(hourly, "surface_pressure")

        return [
            WeatherRecord(
                ts=_parse_ts(times[i]),
                temp=temp[i],
                humidity=humidity[i],
                wind_speed=wind_speed[i],
                wind_dir=wind_dir[i],
                pressure=pressure[i],
            )
            for i in range(len(times))
        ]
