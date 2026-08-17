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
    assert set(kc) == {
        "id", "sport", "abbr", "name", "conference", "division", "logo_url",
        "tier", "color", "alt_color",
    }
    assert kc["sport"] == "NFL"
    assert kc["logo_url"] == "https://a.espncdn.com/i/teamlogos/nfl/500/kc.png"


def test_schedule_contract(client):
    response = client.get("/api/schedule?season=2026")
    assert response.status_code == 200
    body = response.json()
    assert body["season"] == 2026
    assert body["sport"] == "NFL"
    assert [w["week"] for w in body["weeks"]] == [1]
    game = next(
        g for g in body["weeks"][0]["games"] if g["game_id"] == "2026_01_BUF_KC"
    )
    nfl_extras = {"rank": None, "conference": None, "logo_url": None, "color": None}
    assert game["home"] == {"abbr": "KC", "name": "Chiefs", **nfl_extras}
    assert game["away"] == {"abbr": "BUF", "name": "Bills", **nfl_extras}
    assert game["sport"] == "NFL"
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
    assert body["prediction_status"] == "ready"
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
    assert body["model_version"] == "1.0.0"


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
        assert detail["prediction_status"] == "ready"
        assert detail["narrative"] is not None
        assert client.get("/api/predictions/unknown").status_code == 404
    finally:
        monkeypatch.setattr(get_settings(), "blitzcast_mock", False)


def test_sport_omitted_returns_nfl_only(client):
    """CFB rows are seeded, but sport-less requests stay NFL-only."""
    teams = client.get("/api/teams").json()
    assert {t["abbr"] for t in teams} == {"KC", "BUF", "PHI", "DAL"}
    body = client.get("/api/schedule?season=2026").json()
    game_ids = [g["game_id"] for w in body["weeks"] for g in w["games"]]
    assert game_ids and not any(g.startswith("cfb_") for g in game_ids)


def test_teams_cfb(client):
    response = client.get("/api/teams?sport=CFB")
    assert response.status_code == 200
    teams = response.json()
    assert [t["abbr"] for t in teams] == ["ALA", "MER", "UGA"]
    ala = teams[0]
    assert ala["sport"] == "CFB"
    assert ala["tier"] == "FBS"
    assert ala["division"] is None
    assert ala["color"] == "#9E1B32"
    assert ala["logo_url"] == "https://a.espncdn.com/i/teamlogos/ncaa/500/333.png"
    mer = teams[1]
    assert mer["tier"] == "FCS"
    assert mer["logo_url"] is None  # no espn_id, no stored logo


def test_sport_lowercase_accepted(client):
    games = client.get("/api/games?week=1&season=2026&sport=cfb").json()
    assert [g["game_id"] for g in games] == ["cfb_401800001"]
    game = games[0]
    assert game["sport"] == "CFB"
    # AP poll entering week 1 wins over Coaches.
    assert game["home"]["rank"] == 7 and game["home"]["abbr"] == "ALA"
    assert game["away"]["rank"] == 3 and game["away"]["abbr"] == "UGA"
    assert game["home"]["conference"] == "SEC"
    assert game["home"]["color"] == "#9E1B32"


def test_unknown_sport_rejected(client):
    for path in ("/api/teams?sport=XFL", "/api/schedule?sport=nba", "/api/games?week=1&sport=x"):
        assert client.get(path).status_code == 422


def test_schedule_cfb_includes_tbd_kickoff(client):
    body = client.get("/api/schedule?season=2026&sport=CFB").json()
    assert body["sport"] == "CFB"
    assert [w["week"] for w in body["weeks"]] == [1, 2]
    tbd = body["weeks"][1]["games"][0]
    assert tbd["game_id"] == "cfb_401800002"
    assert tbd["kickoff"] is None
    assert tbd["home"]["rank"] is None  # no poll rows for week 2


def test_prediction_detail_cfb(client):
    response = client.get("/api/predictions/cfb_401800001")
    assert response.status_code == 200
    body = response.json()
    assert body["sport"] == "CFB"
    assert body["prediction_status"] == "ready"
    assert body["model_version"] == "cfb-1.0.0"
    assert body["home"]["rank"] == 7
    assert body["away"]["rank"] == 3
    assert body["home"]["conference"] == "SEC"
    assert body["home"]["color"] == "#9E1B32"
    assert body["home"]["logo_url"] == "https://a.espncdn.com/i/teamlogos/ncaa/500/333.png"
    assert body["home"]["name"] == "Alabama"  # no NFL nickname stripping
    assert body["home"]["win_prob"] == 0.55
    assert body["away"]["win_prob"] == 0.45
    assert body["factors"][0]["label"] == "AP poll standing edge"


def test_prediction_detail_cfb_tbd_pending(client):
    body = client.get("/api/predictions/cfb_401800002").json()
    assert body["sport"] == "CFB"
    assert body["prediction_status"] == "pending"
    assert body["kickoff"] is None
    # NULL kickoff: record falls back to game_date, not an error.
    assert body["home"]["record"] == "0-0"
    assert body["away"]["logo_url"] is None


def test_mock_mode_cfb(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "blitzcast_mock", True)
    try:
        teams = client.get("/api/teams?sport=cfb").json()
        assert len(teams) == 5
        assert all(t["sport"] == "CFB" for t in teams)
        body = client.get("/api/schedule?season=2026&sport=CFB").json()
        assert [w["week"] for w in body["weeks"]] == [1, 2]
        ranked = client.get("/api/predictions/cfb_401752873").json()
        assert ranked["sport"] == "CFB"
        assert ranked["prediction_status"] == "ready"
        assert ranked["home"]["rank"] == 1
        assert ranked["narrative"] is not None
        tbd = client.get("/api/predictions/cfb_401753120").json()
        assert tbd["kickoff"] is None
        assert tbd["prediction_status"] == "pending"
        # NFL mock is untouched by sport param default.
        assert len(client.get("/api/teams").json()) == 32
    finally:
        monkeypatch.setattr(get_settings(), "blitzcast_mock", False)
