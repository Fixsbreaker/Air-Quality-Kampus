"""Тесты клиента Open-Meteo, адаптера Airkaz и записи в базу."""

from __future__ import annotations

from datetime import datetime

import httpx
import pytest
import respx
from sqlalchemy import select

from app.config import settings
from app.ingestion.airkaz import haversine_km, parse_stations
from app.ingestion.openmeteo import OpenMeteoClient, OpenMeteoError
from app.ingestion.repository import upsert_measurements, upsert_weather
from app.locations import DEFAULT_LOCATION
from app.models import Measurement, Weather

AQ_PAYLOAD = {
    "hourly": {
        "time": ["2026-08-07T00:00", "2026-08-07T01:00", "2026-08-07T02:00"],
        "pm2_5": [12.4, 18.9, None],
        "pm10": [25.0, 33.1, 40.2],
        "nitrogen_dioxide": [8.0, 9.5, 10.0],
        "ozone": [55.0, 60.0, 62.0],
    }
}

WEATHER_PAYLOAD = {
    "hourly": {
        "time": ["2026-08-07T00:00", "2026-08-07T01:00"],
        "temperature_2m": [21.5, 20.0],
        "relative_humidity_2m": [40, 45],
        "wind_speed_10m": [3.2, 2.8],
        "wind_direction_10m": [180, 200],
        "surface_pressure": [910.0, 911.0],
    }
}


class TestOpenMeteoClient:
    @respx.mock
    def test_parses_air_quality(self):
        respx.get(settings.open_meteo_aq_url).mock(
            return_value=httpx.Response(200, json=AQ_PAYLOAD)
        )
        with OpenMeteoClient() as client:
            records = client.fetch_air_quality(43.2364, 76.9457)

        assert len(records) == 3
        assert records[0].ts == datetime(2026, 8, 7, 0, 0)
        assert records[0].pm25 == 12.4
        assert records[2].pm25 is None  # пропуск источника сохраняется как None

    @respx.mock
    def test_parses_weather(self):
        respx.get(settings.open_meteo_weather_url).mock(
            return_value=httpx.Response(200, json=WEATHER_PAYLOAD)
        )
        with OpenMeteoClient() as client:
            records = client.fetch_weather(43.2364, 76.9457)

        assert len(records) == 2
        assert records[0].temp == 21.5
        assert records[0].humidity == 40
        assert records[1].wind_dir == 200

    @respx.mock
    def test_missing_column_becomes_none(self):
        payload = {"hourly": {"time": ["2026-08-07T00:00"], "pm2_5": [10.0]}}
        respx.get(settings.open_meteo_aq_url).mock(return_value=httpx.Response(200, json=payload))
        with OpenMeteoClient() as client:
            records = client.fetch_air_quality(43.2364, 76.9457)

        assert records[0].pm10 is None

    @respx.mock
    def test_retries_then_raises(self):
        route = respx.get(settings.open_meteo_aq_url).mock(return_value=httpx.Response(500))
        with OpenMeteoClient(retries=3) as client, pytest.raises(OpenMeteoError):
            client.fetch_air_quality(43.2364, 76.9457)

        assert route.call_count == 3

    @respx.mock
    def test_recovers_on_second_attempt(self):
        respx.get(settings.open_meteo_aq_url).mock(
            side_effect=[httpx.Response(503), httpx.Response(200, json=AQ_PAYLOAD)]
        )
        with OpenMeteoClient(retries=3) as client:
            records = client.fetch_air_quality(43.2364, 76.9457)

        assert len(records) == 3

    @respx.mock
    def test_api_error_field_is_reported(self):
        respx.get(settings.open_meteo_aq_url).mock(
            return_value=httpx.Response(200, json={"error": True, "reason": "Invalid date"})
        )
        with OpenMeteoClient() as client, pytest.raises(OpenMeteoError, match="Invalid date"):
            client.fetch_air_quality(43.2364, 76.9457)


class TestAirkaz:
    def test_haversine_known_distance(self):
        # Между главным корпусом и домом студентов примерно 5 км
        assert 3.0 < haversine_km(43.2364, 76.9457, 43.2141, 76.9099) < 6.0

    def test_filters_by_radius(self):
        payload = [
            {"name": "рядом", "lat": 43.2370, "lng": 76.9460, "pm25": 30, "pm10": 45},
            {"name": "далеко", "lat": 43.4000, "lng": 77.2000, "pm25": 10, "pm10": 15},
        ]
        readings = parse_stations(payload, 43.2364, 76.9457, radius_km=3.0)
        assert [item.station for item in readings] == ["рядом"]

    def test_broken_rows_are_skipped(self):
        payload = [{"name": "без координат", "pm25": 30}, {"lat": "x", "lng": "y"}]
        assert parse_stations(payload, 43.2364, 76.9457) == []

    def test_disabled_source_returns_empty(self):
        from app.ingestion.airkaz import fetch_nearby

        assert fetch_nearby(43.2364, 76.9457) == []  # AIRKAZ_ENABLED=false в тестах


class TestRepository:
    def test_insert_computes_aqi(self, db):
        from app.ingestion.openmeteo import AirQualityRecord

        records = [AirQualityRecord(ts=datetime(2026, 8, 7, 0), pm25=55.5, pm10=20.0, no2=1, o3=2)]
        stats = upsert_measurements(db, DEFAULT_LOCATION, "open-meteo", records)
        db.commit()

        row = db.scalars(select(Measurement)).one()
        assert stats.inserted == 1
        assert row.aqi == 151
        assert row.aqi_category == "Вредно"
        assert row.dominant_pollutant == "pm25"

    def test_upsert_is_idempotent(self, db):
        from app.ingestion.openmeteo import AirQualityRecord

        records = [AirQualityRecord(ts=datetime(2026, 8, 7, 0), pm25=10.0, pm10=20.0, no2=1, o3=2)]
        upsert_measurements(db, DEFAULT_LOCATION, "open-meteo", records)
        db.commit()

        updated = [AirQualityRecord(ts=datetime(2026, 8, 7, 0), pm25=99.0, pm10=20.0, no2=1, o3=2)]
        stats = upsert_measurements(db, DEFAULT_LOCATION, "open-meteo", updated)
        db.commit()

        rows = db.scalars(select(Measurement)).all()
        assert len(rows) == 1
        assert stats.updated == 1
        assert rows[0].pm25 == 99.0

    def test_weather_upsert(self, db):
        from app.ingestion.openmeteo import WeatherRecord

        records = [
            WeatherRecord(
                ts=datetime(2026, 8, 7, 0),
                temp=20.0,
                humidity=50.0,
                wind_speed=3.0,
                wind_dir=180.0,
                pressure=910.0,
            )
        ]
        upsert_weather(db, DEFAULT_LOCATION, records)
        db.commit()

        row = db.scalars(select(Weather)).one()
        assert row.temp == 20.0
        assert row.location == DEFAULT_LOCATION.code

    def test_empty_input_is_noop(self, db):
        stats = upsert_measurements(db, DEFAULT_LOCATION, "open-meteo", [])
        assert stats.inserted == 0
        assert db.scalars(select(Measurement)).all() == []
