"""Общие фикстуры тестов.

Тесты идут на SQLite: он поднимается мгновенно и не требует Docker, а все
модели написаны на переносимых типах (см. docstring в app/models.py).
Переменные окружения выставляются до импорта приложения, потому что
настройки кэшируются при первом обращении.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

TEST_DB = Path(tempfile.gettempdir()) / "kbtu_aqi_test.sqlite3"
TEST_MODELS = Path(tempfile.mkdtemp(prefix="kbtu_aqi_models_"))

os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{TEST_DB}"
os.environ["MODEL_DIR"] = str(TEST_MODELS)
os.environ["APP_ENV"] = "test"
os.environ["ADMIN_TOKEN"] = "test-admin-token"
os.environ["AIRKAZ_ENABLED"] = "false"
os.environ["AQI_BREAKPOINTS"] = "epa_2024"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import SessionLocal, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, Measurement, Weather, utcnow  # noqa: E402
from app.services.aqi import compute_aqi  # noqa: E402

ADMIN_HEADERS = {"X-Admin-Token": "test-admin-token"}


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    if TEST_DB.exists():
        TEST_DB.unlink()
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    if TEST_DB.exists():
        TEST_DB.unlink()


@pytest.fixture
def db() -> Session:
    """Чистая база на каждый тест."""
    session = SessionLocal()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(db: Session) -> TestClient:
    """TestClient, работающий с той же сессией, что и фикстура db."""

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ----------------------------------------------------------------- фабрики


def make_measurement(
    ts: datetime,
    *,
    location: str = "main",
    pm25: float | None = 20.0,
    pm10: float | None = 30.0,
    source: str = "open-meteo",
) -> Measurement:
    result = compute_aqi(pm25, pm10)
    return Measurement(
        ts=ts,
        source=source,
        location=location,
        lat=43.2364,
        lon=76.9457,
        pm25=pm25,
        pm10=pm10,
        no2=12.0,
        o3=40.0,
        aqi=result.aqi if result else None,
        aqi_category=result.category if result else None,
        dominant_pollutant=result.dominant_pollutant if result else None,
    )


@pytest.fixture
def seeded_db(db: Session) -> Session:
    """Сутки часовых наблюдений и погоды по главному корпусу."""
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    for hours_back in range(24, 0, -1):
        ts = now - timedelta(hours=hours_back)
        db.add(make_measurement(ts, pm25=10 + hours_back % 12, pm10=20 + hours_back % 15))
        db.add(
            Weather(
                ts=ts,
                location="main",
                temp=15.0,
                wind_speed=3.0,
                wind_dir=180.0,
                humidity=50.0,
                pressure=910.0,
            )
        )
    db.add(make_measurement(now, pm25=18.4, pm10=33.0))
    db.commit()
    return db
