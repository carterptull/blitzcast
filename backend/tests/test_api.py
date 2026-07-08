"""API contract tests against a seeded SQLite database."""


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_teams_contract(client):
    response = client.get("/api/teams")
    assert response.status_code == 200
    teams = response.json()
    assert len(teams) == 4
    kc = next(t for t in teams if t["abbr"] == "KC")
    assert set(kc) == {"id", "abbr", "name", "conference", "division", "logo_url"}
    assert kc["logo_url"] == "https://a.espncdn.com/i/teamlogos/nfl/500/kc.png"


def test_schedule_contract(client):
    response = client.get("/api/schedule?season=2026")
    assert response.status_code == 200
    body = response.json()
    assert body["season"] == 2026
    assert [w["week"] for w in body["weeks"]] == [1]
    game = next(
        g for g in body["weeks"][0]["games"] if g["game_id"] == "2026_01_BUF_KC"
    )
    assert game["home"] == {"abbr": "KC", "name": "Chiefs"}
    assert game["away"] == {"abbr": "BUF", "name": "Bills"}
    assert game["is_primetime"] is True
    assert game["status"] == "scheduled"
    assert game["has_prediction"] is True
    assert game["home_win_prob"] == 0.61


def test_games_by_week(client):
    response = client.get("/api/games?week=1&season=2026")
    assert response.status_code == 200
    games = response.json()
    assert len(games) == 2
    unpredicted = next(g for g in games if g["game_id"] == "2026_01_PHI_DAL")
    assert unpredicted["has_prediction"] is False
    assert unpredicted["home_win_prob"] is None


def test_prediction_detail_available(client):
    response = client.get("/api/predictions/2026_01_BUF_KC")
    assert response.status_code == 200
    body = response.json()
    assert body["prediction_status"] == "available"
    assert body["home"]["win_prob"] == 0.61
    assert body["away"]["win_prob"] == 0.39
    assert body["home"]["win_prob"] + body["away"]["win_prob"] == 1.0
    # Week 1: records entering the season are 0-0.
    assert body["home"]["record"] == "0-0"
    assert body["away"]["record"] == "0-0"
    assert body["venue"]["name"] == "Test Field"
    assert body["odds"]["spread_home"] == 2.5
    assert body["factors"][0]["label"] == "Team rating (Elo) edge"
    assert body["factors"][0]["direction"] == "home"
    assert body["narrative"] is None
    assert body["model_version"] == "0.1.0"


def test_prediction_detail_pending(client):
    response = client.get("/api/predictions/2026_01_PHI_DAL")
    assert response.status_code == 200
    body = response.json()
    assert body["prediction_status"] == "pending"
    assert body["factors"] == []
    assert body["narrative"] is None
    assert body["home"]["win_prob"] is None


def test_prediction_unknown_game_404(client):
    response = client.get("/api/predictions/2026_99_XX_YY")
    assert response.status_code == 404


def test_mock_mode(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "blitzcast_mock", True)
    try:
        teams = client.get("/api/teams").json()
        assert len(teams) == 32
        detail = client.get("/api/predictions/2026_01_BUF_KC").json()
        assert detail["prediction_status"] == "available"
        assert detail["narrative"] is not None
        assert client.get("/api/predictions/unknown").status_code == 404
    finally:
        monkeypatch.setattr(get_settings(), "blitzcast_mock", False)
