"""Postseason API contract: summary/detail fields, /api/slates, the round filter, mock mode."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models import SPORT_CFB, SPORT_NFL, Game, Team
from app.services.predictions import build_slates

NOW = datetime(2026, 12, 8, 15, 0, tzinfo=UTC)


def _g(week, kickoff, season_type="regular", round_=None, home_score=None, away_score=None):
    return SimpleNamespace(week=week, kickoff_time=kickoff, season_type=season_type,
                           round=round_, home_score=home_score, away_score=away_score)


def _add(db, gid, sport, week, kickoff, season_type="regular", round_=None, event=None,
         neutral=False, seeds=(None, None), game_date=None):
    teams = [t.team_id for t in db.query(Team).filter(Team.sport == sport).limit(2)]
    db.add(Game(game_id=gid, sport=sport, season=2026, week=week,
                game_date=game_date or kickoff.date(), kickoff_time=kickoff,
                home_team_id=teams[0], away_team_id=teams[1], season_type=season_type,
                round=round_, event_name=event, is_neutral_site=neutral,
                home_seed=seeds[0], away_seed=seeds[1]))


def test_game_summary_carries_postseason_fields(client, db):
    """PS-A1: game summaries and matchup detail carry season type, round, event, neutral, seeds."""
    k = datetime(2027, 1, 1, 21, 0, tzinfo=UTC)
    _add(db, "cfb_rose", SPORT_CFB, 17, k, "postseason", "cfp_quarterfinal",
         "Rose Bowl, CFP Quarterfinal", True, (3, 6))
    db.commit()
    (game,) = client.get("/api/games?week=17&season=2026&sport=CFB").json()
    assert game["season_type"] == "postseason"
    assert game["round"] == "cfp_quarterfinal"
    assert game["event_name"] == "Rose Bowl, CFP Quarterfinal"
    assert game["is_neutral_site"] is True
    assert (game["home_seed"], game["away_seed"]) == (3, 6)
    detail = client.get("/api/predictions/cfb_rose").json()
    assert (detail["season_type"], detail["round"], detail["event_name"]) == (
        "postseason", "cfp_quarterfinal", "Rose Bowl, CFP Quarterfinal")
    assert (detail["home_seed"], detail["away_seed"]) == (3, 6)
    regular = client.get("/api/games?week=1&season=2026").json()[0]
    assert regular["season_type"] == "regular" and regular["round"] is None
    assert regular["event_name"] is None and regular["home_seed"] is None


def test_slates_nfl_regular_then_rounds(client, db):
    """PS-A2: NFL slates list regular weeks, then the four rounds keyed by slug."""
    base = datetime(2027, 1, 16, 21, 30, tzinfo=UTC)
    rounds = [("wild_card", "AFC Wild Card"), ("divisional", "AFC Divisional"),
              ("conference", "AFC Championship"), ("super_bowl", "Super Bowl LXI")]
    for i, (rnd, ev) in enumerate(rounds):
        _add(db, f"2026_{19 + i}_X", SPORT_NFL, 19 + i, base + timedelta(days=7 * i),
             "postseason", rnd, ev)
    db.commit()
    slates = client.get("/api/slates?season=2026&sport=NFL").json()
    post = [s for s in slates if s["phase"] == "postseason"]
    assert [s["key"] for s in post] == ["wild-card", "divisional", "conference", "super-bowl"]
    assert [s["short_label"] for s in post] == ["WC", "DIV", "CONF", "SB"]
    assert [s["week"] for s in post] == [19, 20, 21, 22]
    regular = [s for s in slates if s["phase"] == "regular"]
    assert regular
    for s in regular:
        assert s["key"] == "w" + str(s["week"]) and s["group_label"] == "Wk"
    assert slates.index(regular[-1]) < slates.index(post[0])


def test_slates_cfb_champ_week_label():
    """PS-A3: a week with any title game is labeled Conference Championships, even with a stray."""
    k = datetime(2026, 12, 5, 21, 0, tzinfo=UTC)
    (slate,) = build_slates([_g(14, k, round_="conf_championship"), _g(14, k)], NOW)
    assert (slate.key, slate.label, slate.group_label, slate.short_label) == (
        "w14", "Conference Championships", "Champ", "14")
    (plain,) = build_slates([_g(13, k)], NOW)
    assert (plain.label, plain.group_label, plain.short_label) == (None, "Wk", "13")


def test_slates_cfb_postseason_split_by_round():
    """PS-A2: CFB week 17 splits into one slate per round, bowls before the CFP rounds."""
    k = datetime(2026, 12, 20, 1, 0, tzinfo=UTC)
    slates = build_slates([
        _g(17, k, "postseason", "cfp_quarterfinal"), _g(17, k, "postseason", "bowl"),
        _g(17, k, "postseason", "cfp_first_round"), _g(17, k, "postseason", "bowl"),
        _g(15, k - timedelta(days=8)),
    ], NOW)
    assert [s.key for s in slates] == ["w15", "bowls", "cfp-first-round", "cfp-quarterfinals"]
    bowls = slates[1]
    assert (bowls.phase, bowls.week, bowls.round, bowls.game_count) == (
        "postseason", 17, "bowl", 2)
    assert (bowls.label, bowls.group_label, bowls.short_label) == (
        "Bowl Season", "Non-CFP", "Bowls")


def test_slate_kickoff_window_and_unscheduled():
    """PS-A4: next_kickoff is the earliest kickoff after now minus 12h; TBD unscored games flag."""
    games = [
        _g(17, NOW - timedelta(hours=13), "postseason", "bowl", 21, 14),
        _g(17, NOW - timedelta(hours=11), "postseason", "bowl"),
        _g(17, NOW + timedelta(days=3), "postseason", "bowl"),
        _g(17, None, "postseason", "bowl"),
    ]
    (slate,) = build_slates(games, NOW)
    assert slate.next_kickoff == NOW - timedelta(hours=11)
    assert slate.first_kickoff == NOW - timedelta(hours=13)
    assert slate.last_kickoff == NOW + timedelta(days=3)
    assert slate.has_unscheduled is True
    (done,) = build_slates([_g(5, NOW - timedelta(days=3), home_score=1, away_score=0)], NOW)
    assert done.next_kickoff is None and done.has_unscheduled is False


def test_games_round_filter(client, db):
    """PS-A5: week=17&round=bowls returns only bowls."""
    k = datetime(2026, 12, 22, 20, 0, tzinfo=UTC)
    _add(db, "cfb_b1", SPORT_CFB, 17, k, "postseason", "bowl", "Pop-Tarts Bowl", True)
    _add(db, "cfb_r1", SPORT_CFB, 17, k, "postseason", "cfp_first_round", "CFP First Round",
         False, (12, 5))
    db.commit()
    games = client.get("/api/games?week=17&season=2026&sport=CFB&round=bowls").json()
    assert [g["game_id"] for g in games] == ["cfb_b1"]
    both = client.get("/api/games?week=17&season=2026&sport=CFB").json()
    assert {g["game_id"] for g in both} == {"cfb_b1", "cfb_r1"}


@pytest.mark.parametrize("bad", ["bogus", "BOWLS", "wild_card", "a" * 30, "bowls;drop"])
def test_games_bad_round_slug_422(client, bad):
    """PS-A5: an unknown or malformed round slug is rejected with 422."""
    assert client.get(f"/api/games?week=17&season=2026&round={bad}").status_code == 422


def test_slates_reject_bad_input(client):
    """PS-A2: slates validate sport and season like the schedule endpoint."""
    assert client.get("/api/slates?sport=XFL").status_code == 422
    assert client.get("/api/slates?season=1800").status_code == 422


def test_mock_mode_slates_and_postseason_fixtures(client, monkeypatch):
    """PS-A6: mock mode serves postseason slates and fixtures for both sports."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "blitzcast_mock", True)
    try:
        nfl = client.get("/api/slates?season=2026&sport=NFL").json()
        assert [s["key"] for s in nfl if s["phase"] == "postseason"] == [
            "wild-card", "divisional", "conference", "super-bowl"]
        cfb = client.get("/api/slates?season=2026&sport=CFB").json()
        keys = {s["key"] for s in cfb}
        assert {"w14", "bowls", "cfp-first-round", "cfp-quarterfinals"} <= keys
        assert next(s for s in cfb if s["key"] == "w14")["label"] == "Conference Championships"
        sb = client.get("/api/games?week=22&season=2026").json()
        assert sb[0]["event_name"] == "Super Bowl LXI" and sb[0]["is_neutral_site"] is True
        bowls = client.get("/api/games?week=17&season=2026&sport=CFB&round=bowls").json()
        assert bowls and all(g["round"] == "bowl" for g in bowls)
        assert any(g["kickoff"] is None for g in bowls)
        r1 = client.get(
            "/api/games?week=17&season=2026&sport=CFB&round=cfp-first-round").json()
        assert r1 and all(g["home_seed"] and g["away_seed"] for g in r1)
        detail = client.get(f"/api/predictions/{sb[0]['game_id']}").json()
        assert detail["event_name"] == "Super Bowl LXI"
        assert detail["venue"]["is_neutral_site"] is True
    finally:
        monkeypatch.setattr(get_settings(), "blitzcast_mock", False)


def test_game_date_only_postseason_game_is_unscheduled(client, db):
    """PS-A4: a postseason game with no kickoff counts as unscheduled on its slate."""
    _add(db, "cfb_tbd", SPORT_CFB, 17, None, "postseason", "bowl", "Bowl game", True,
         game_date=date(2026, 12, 23))
    db.commit()
    bowls = next(s for s in client.get("/api/slates?season=2026&sport=CFB").json()
                 if s["key"] == "bowls")
    assert bowls["has_unscheduled"] is True and bowls["game_count"] == 1
