"""Param validation, docs gating, CORS, nosniff and the TTL cache."""

import threading

import pytest
from fastapi.testclient import TestClient

from app import cache
from app.config import Settings, get_settings
from app.main import create_app


@pytest.mark.parametrize(
    "path",
    [
        "/api/predictions/a%00b",
        "/api/predictions/" + "a" * 33,
        "/api/predictions/bad.id",
        "/api/schedule?season=99999",
        "/api/schedule?season=1999",
        "/api/record?season=99999",
        "/api/games?week=99&season=2026",
        "/api/games?week=-1&season=2026",
        "/api/games?week=1&season=99999",
    ],
)
def test_invalid_params_are_422(client, path):
    assert client.get(path).status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "/api/predictions/2026_01_BUF_KC",
        "/api/predictions/cfb_401800001",
        "/api/predictions/2026_03_KC_DAL_NEUTRAL",
        "/api/games?week=0&season=2026",
        "/api/games?week=30&season=2100",
    ],
)
def test_legitimate_params_pass_validation(client, path):
    assert client.get(path).status_code in (200, 404)


def test_docs_off_by_default():
    assert Settings.model_fields["api_docs"].default is False
    app = create_app(Settings(_env_file=None, api_docs=False))
    with TestClient(app) as c:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert c.get(path).status_code == 404
        assert c.get("/health").status_code == 200


def test_docs_on_when_enabled():
    app = create_app(Settings(_env_file=None, api_docs=True))
    with TestClient(app) as c:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert c.get(path).status_code == 200


def test_cors_rejects_post_and_credentials(client):
    origin = get_settings().cors_origin_list[0]
    preflight = client.options(
        "/api/schedule",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )
    assert preflight.status_code == 400
    ok = client.options(
        "/api/schedule",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-credentials" not in ok.headers
    simple = client.get("/health", headers={"Origin": origin})
    assert "access-control-allow-credentials" not in simple.headers


@pytest.mark.parametrize(
    "path", ["/health", "/api/teams", "/api/predictions/nope", "/api/schedule?season=99999"]
)
def test_nosniff_on_every_response(client, path):
    assert client.get(path).headers["x-content-type-options"] == "nosniff"


def _spy_schedule(monkeypatch):
    from app.services import predictions as svc

    calls: list[tuple] = []
    real = svc.get_schedule

    def spy(db, season, sport, status):
        calls.append((season, sport, status))
        return real(db, season, sport, status)

    monkeypatch.setattr(svc, "get_schedule", spy)
    return calls


def test_schedule_is_cached_per_params(client, monkeypatch):
    calls = _spy_schedule(monkeypatch)
    first = client.get("/api/schedule?season=2026").json()
    assert client.get("/api/schedule?season=2026").json() == first
    assert len(calls) == 1
    client.get("/api/schedule?season=2025")
    client.get("/api/schedule?season=2026&sport=CFB")
    client.get("/api/schedule?season=2026&status=final")
    assert len(calls) == 4


def test_record_is_cached_per_params(client, monkeypatch):
    from app.services import predictions as svc

    calls: list[tuple] = []
    real = svc.get_record

    def spy(db, season, sport):
        calls.append((season, sport))
        return real(db, season=season, sport=sport)

    monkeypatch.setattr(svc, "get_record", spy)
    client.get("/api/record?season=2026")
    client.get("/api/record?season=2026")
    assert len(calls) == 1
    client.get("/api/record?season=2026&sport=CFB")
    client.get("/api/record?season=2025")
    assert len(calls) == 3


def test_cache_is_clear_at_test_start(client, monkeypatch):
    """The autouse fixture empties the cache, so this call must compute."""
    calls = _spy_schedule(monkeypatch)
    client.get("/api/schedule?season=2026")
    assert len(calls) == 1


def test_cache_ttl_expiry_and_eviction(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(cache.time, "monotonic", lambda: now[0])
    runs = []

    def compute():
        runs.append(1)
        return len(runs)

    assert cache.cached(("k",), 60, compute) == 1
    assert cache.cached(("k",), 60, compute) == 1
    now[0] += 61
    assert cache.cached(("k",), 60, compute) == 2

    cache.clear()
    for i in range(cache.MAX_ENTRIES + 10):
        cache.cached(("e", i), 60, lambda i=i: i)
    assert len(cache._entries) == cache.MAX_ENTRIES
    assert ("e", 0) not in cache._entries
    assert ("e", cache.MAX_ENTRIES + 9) in cache._entries


def test_cache_is_thread_safe():
    errors: list[Exception] = []

    def worker(n: int) -> None:
        try:
            for i in range(300):
                k = (n + i) % 400
                assert cache.cached(("t", k), 60, lambda k=k: k) == k
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(cache._entries) <= cache.MAX_ENTRIES
