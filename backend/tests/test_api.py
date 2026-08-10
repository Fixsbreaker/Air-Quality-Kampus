"""Тесты HTTP API."""

from __future__ import annotations

from datetime import timedelta

from app.models import Forecast, User, utcnow
from tests.conftest import ADMIN_HEADERS, make_measurement


class TestMeta:
    def test_root(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["docs"] == "/docs"

    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["database"] == "ok"

    def test_locations(self, client):
        response = client.get("/api/locations")
        assert response.status_code == 200
        codes = [item["code"] for item in response.json()]
        assert "main" in codes

    def test_openapi_schema_is_generated(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        paths = response.json()["paths"]
        for endpoint in ("/api/current", "/api/history", "/api/forecast", "/api/subscribe"):
            assert endpoint in paths


class TestCurrent:
    def test_returns_latest_observation(self, client, seeded_db):
        response = client.get("/api/current")
        assert response.status_code == 200

        body = response.json()
        assert body["location"]["code"] == "main"
        assert body["aqi"] is not None
        assert body["recommendation"]["text"]
        assert body["stale"] is False

    def test_future_rows_are_ignored(self, client, db):
        now = utcnow().replace(minute=0, second=0, microsecond=0)
        db.add(make_measurement(now - timedelta(hours=1), pm25=10.0))
        db.add(make_measurement(now + timedelta(hours=5), pm25=300.0))
        db.commit()

        body = client.get("/api/current").json()
        assert body["pm25"] == 10.0

    def test_stale_flag(self, client, db):
        db.add(make_measurement(utcnow() - timedelta(hours=10), pm25=10.0))
        db.commit()
        assert client.get("/api/current").json()["stale"] is True

    def test_404_when_no_data(self, client):
        assert client.get("/api/current").status_code == 404

    def test_unknown_location(self, client):
        assert client.get("/api/current", params={"location": "mars"}).status_code == 404


class TestHistory:
    def test_default_window(self, client, seeded_db):
        body = client.get("/api/history").json()
        assert body["count"] == 25
        assert body["points"][0]["ts"] < body["points"][-1]["ts"]

    def test_explicit_range(self, client, seeded_db):
        now = utcnow()
        response = client.get(
            "/api/history",
            params={
                "from": (now - timedelta(hours=5)).isoformat(),
                "to": now.isoformat(),
            },
        )
        assert response.status_code == 200
        assert response.json()["count"] <= 6

    def test_reversed_range_is_rejected(self, client):
        now = utcnow()
        response = client.get(
            "/api/history",
            params={"from": now.isoformat(), "to": (now - timedelta(hours=1)).isoformat()},
        )
        assert response.status_code == 422

    def test_too_wide_range_is_rejected(self, client):
        now = utcnow()
        response = client.get(
            "/api/history",
            params={"from": (now - timedelta(days=400)).isoformat(), "to": now.isoformat()},
        )
        assert response.status_code == 422

    def test_empty_result_is_not_an_error(self, client):
        body = client.get("/api/history").json()
        assert body["count"] == 0
        assert body["points"] == []


class TestForecast:
    def _seed(self, db, hours: int = 3, version: str = "lightgbm-test"):
        now = utcnow().replace(minute=0, second=0, microsecond=0)
        for horizon in range(1, hours + 1):
            db.add(
                Forecast(
                    created_at=now,
                    target_ts=now + timedelta(hours=horizon),
                    location="main",
                    horizon_h=horizon,
                    pm25_pred=10.0 * horizon,
                    aqi_pred=40 * horizon,
                    aqi_category="Хорошо",
                    model_version=version,
                )
            )
        db.commit()

    def test_returns_points_and_worst_hour(self, client, db):
        self._seed(db)
        body = client.get("/api/forecast").json()

        assert len(body["points"]) == 3
        assert body["model_version"] == "lightgbm-test"
        assert body["worst"]["aqi_pred"] == 120

    def test_404_without_forecast(self, client):
        assert client.get("/api/forecast").status_code == 404

    def test_hours_parameter_is_validated(self, client):
        assert client.get("/api/forecast", params={"hours": 0}).status_code == 422
        assert client.get("/api/forecast", params={"hours": 500}).status_code == 422


class TestSubscriptions:
    def test_subscribe_creates_then_updates(self, client, db):
        first = client.post("/api/subscribe", json={"tg_id": 111, "threshold_aqi": 120})
        assert first.status_code == 200
        assert first.json()["created"] is True

        second = client.post("/api/subscribe", json={"tg_id": 111, "threshold_aqi": 80})
        assert second.json()["created"] is False
        assert second.json()["threshold_aqi"] == 80

        assert db.query(User).count() == 1

    def test_validation(self, client):
        assert client.post("/api/subscribe", json={"tg_id": -1}).status_code == 422
        assert (
            client.post("/api/subscribe", json={"tg_id": 5, "threshold_aqi": 900}).status_code
            == 422
        )
        assert (
            client.post("/api/subscribe", json={"tg_id": 5, "location": "mars"}).status_code == 422
        )

    def test_unsubscribe(self, client):
        client.post("/api/subscribe", json={"tg_id": 222})
        response = client.post("/api/unsubscribe", params={"tg_id": 222})
        assert response.status_code == 200
        assert response.json()["subscribed"] is False

    def test_unsubscribe_unknown_user(self, client):
        assert client.post("/api/unsubscribe", params={"tg_id": 999}).status_code == 404

    def test_subscribers_require_token(self, client):
        client.post("/api/subscribe", json={"tg_id": 333})
        assert client.get("/api/subscribers").status_code == 401
        assert client.get("/api/subscribers", headers={"X-Admin-Token": "wrong"}).status_code == 401

        response = client.get("/api/subscribers", headers=ADMIN_HEADERS)
        assert response.status_code == 200
        assert response.json()[0]["tg_id"] == 333

    def test_unsubscribed_users_are_hidden(self, client):
        client.post("/api/subscribe", json={"tg_id": 444})
        client.post("/api/unsubscribe", params={"tg_id": 444})
        assert client.get("/api/subscribers", headers=ADMIN_HEADERS).json() == []


class TestAdminReport:
    def test_requires_token(self, client):
        assert client.get("/api/admin/report").status_code == 401

    def test_csv_content(self, client, seeded_db):
        response = client.get("/api/admin/report", headers=ADMIN_HEADERS)
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]

        lines = [line for line in response.text.splitlines() if line]
        assert lines[0].startswith("ts_utc;ts_almaty;location")
        assert len(lines) == 26  # заголовок + 25 наблюдений
        assert "Норма; чувствительным людям" in response.text

    def test_location_filter(self, client, seeded_db):
        response = client.get(
            "/api/admin/report", headers=ADMIN_HEADERS, params={"location": "dorm"}
        )
        assert len([line for line in response.text.splitlines() if line]) == 1

    def test_unknown_location(self, client):
        response = client.get(
            "/api/admin/report", headers=ADMIN_HEADERS, params={"location": "mars"}
        )
        assert response.status_code == 404

    def test_models_history_is_protected(self, client):
        assert client.get("/api/admin/models").status_code == 401
        assert client.get("/api/admin/models", headers=ADMIN_HEADERS).status_code == 200
