"""Тесты кэша на Redis.

Главное, что здесь проверяется, — кэш не является точкой отказа. Тесты идут
без запущенного Redis: часть случаев проверяется на выключенном кэше, часть —
на подставном клиенте, который имитирует поведение сервера, включая сбои.
"""

from __future__ import annotations

import pytest

from app.cache import Cache, build_key


class FakeRedis:
    """Минимальная подделка Redis: словарь плюс возможность сломаться."""

    def __init__(self, fail: bool = False):
        self.store: dict[str, str] = {}
        self.fail = fail
        self.ttls: dict[str, int] = {}

    def _maybe_fail(self):
        if self.fail:
            raise ConnectionError("Redis недоступен")

    def get(self, key):
        self._maybe_fail()
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self._maybe_fail()
        self.store[key] = value
        self.ttls[key] = ttl

    def delete(self, key):
        self._maybe_fail()
        self.store.pop(key, None)

    def scan_iter(self, match="*", count=100):
        self._maybe_fail()
        prefix = match.rstrip("*")
        return [key for key in list(self.store) if key.startswith(prefix)]

    def close(self):
        pass


@pytest.fixture
def cache() -> Cache:
    instance = Cache(enabled=False)
    instance._client = FakeRedis()  # noqa: SLF001 - подстановка клиента в тесте
    return instance


class TestBuildKey:
    def test_joins_parts_with_namespace(self):
        assert build_key("current", "main") == "aqi:current:main"

    def test_accepts_numbers(self):
        assert build_key("forecast", "main", 48) == "aqi:forecast:main:48"


class TestDisabledCache:
    """Выключенный кэш ведёт себя как отсутствующий, но не ломает вызовы."""

    def test_reports_unavailable(self):
        assert Cache(enabled=False).available is False

    def test_get_returns_none(self):
        assert Cache(enabled=False).get("aqi:current:main") is None

    def test_set_returns_false(self):
        assert Cache(enabled=False).set("aqi:current:main", {"aqi": 50}) is False

    def test_delete_prefix_returns_zero(self):
        assert Cache(enabled=False).delete_prefix("aqi:") == 0


class TestRoundTrip:
    def test_value_survives_write_and_read(self, cache):
        assert cache.set("aqi:current:main", {"aqi": 68, "category": "Умеренно"}) is True
        assert cache.get("aqi:current:main") == {"aqi": 68, "category": "Умеренно"}

    def test_cyrillic_is_not_escaped(self, cache):
        cache.set("aqi:current:main", {"category": "Умеренно"})
        assert "Умеренно" in cache._client.store["aqi:current:main"]  # noqa: SLF001

    def test_ttl_is_applied(self, cache):
        cache.set("aqi:current:main", {"aqi": 1}, ttl=42)
        assert cache._client.ttls["aqi:current:main"] == 42  # noqa: SLF001

    def test_missing_key_returns_none(self, cache):
        assert cache.get("aqi:current:unknown") is None

    def test_delete_prefix_removes_matching_keys(self, cache):
        cache.set("aqi:current:main", {"aqi": 1})
        cache.set("aqi:current:dorm_ozala", {"aqi": 2})
        cache.set("aqi:forecast:main:48", {"points": []})

        removed = cache.delete_prefix("aqi:current")

        assert removed == 2
        assert cache.get("aqi:current:main") is None
        assert cache.get("aqi:forecast:main:48") == {"points": []}


class TestGracefulDegradation:
    """Сбой Redis не должен превращаться в ошибку у пользователя."""

    @pytest.fixture
    def broken(self) -> Cache:
        instance = Cache(enabled=False)
        instance._client = FakeRedis(fail=True)  # noqa: SLF001
        return instance

    def test_get_swallows_connection_error(self, broken):
        assert broken.get("aqi:current:main") is None

    def test_set_reports_failure_without_raising(self, broken):
        assert broken.set("aqi:current:main", {"aqi": 1}) is False

    def test_delete_prefix_swallows_error(self, broken):
        assert broken.delete_prefix("aqi:") == 0

    def test_corrupted_value_returns_none(self, cache):
        cache._client.store["aqi:current:main"] = "{не json"  # noqa: SLF001
        assert cache.get("aqi:current:main") is None

    def test_unreachable_server_degrades_on_init(self):
        # Порт заведомо закрыт: конструктор обязан отработать без исключения.
        instance = Cache(url="redis://127.0.0.1:6399/0", enabled=True)
        assert instance.available is False
        assert instance.get("aqi:current:main") is None
