"""NFL schedule loader tests: nflverse's whole-week placeholder gametime
must not be presented as a confirmed kickoff."""

import pandas as pd

from app.models import SPORT_NFL, Game
from data_pipeline.games_loader import _kickoff_utc, upsert_games


def _row(game_id, season, week, gameday, gametime, home="KC", away="BUF"):
    return {
        "game_id": game_id, "season": season, "week": week, "gameday": gameday,
        "gametime": gametime, "home_team": home, "away_team": away, "location": "Home",
        "home_score": None, "away_score": None, "div_game": False,
        "spread_line": None, "total_line": None, "home_moneyline": None, "away_moneyline": None,
        "stadium": None,
    }


def test_neutral_site_game_captures_venue_name_and_flag(db):
    """A neutral-site row (nflverse location='Neutral') must not silently
    drop its venue — stadium_id stays NULL (no home team's stadium
    applies) but the raw venue name and a neutral-site flag are kept."""
    row = _row("2026_01_BUF_KC", 2026, 1, "2026-09-10", "20:35", "KC", "BUF")
    row["location"] = "Neutral"
    row["stadium"] = "Melbourne Cricket Ground"
    schedules = pd.DataFrame([row])
    upsert_games(db, schedules)
    game = db.query(Game).filter(Game.game_id == "2026_01_BUF_KC").one()
    assert game.stadium_id is None
    assert game.venue_name == "Melbourne Cricket Ground"
    assert game.is_neutral_site is True


def test_home_game_still_gets_venue_name(db):
    """Non-neutral games also get venue_name populated (from the same
    nflverse column), just with is_neutral_site False."""
    row = _row("2026_03_D", 2026, 3, "2026-09-24", "13:00", "KC", "BUF")
    row["stadium"] = "GEHA Field at Arrowhead Stadium"
    schedules = pd.DataFrame([row])
    upsert_games(db, schedules)
    game = db.query(Game).filter(Game.game_id == "2026_03_D").one()
    assert game.is_neutral_site is False
    assert game.venue_name == "GEHA Field at Arrowhead Stadium"


def test_week_with_uniform_gametime_treated_as_tbd(db):
    """A week where every game shares one gametime is nflverse's not-yet-scheduled
    placeholder, not a real simultaneous kickoff — must not be presented as confirmed."""
    schedules = pd.DataFrame([
        _row("2026_18_A", 2026, 18, "2027-01-10", "13:00", "KC", "BUF"),
        _row("2026_18_B", 2026, 18, "2027-01-10", "13:00", "PHI", "DAL"),
        _row("2026_18_C", 2026, 18, "2027-01-10", "13:00", "DAL", "KC"),
    ])
    upsert_games(db, schedules)
    games = {
        g.game_id: g for g in db.query(Game).filter(
            Game.sport == SPORT_NFL, Game.season == 2026, Game.week == 18
        )
    }
    assert len(games) == 3
    assert all(g.kickoff_time is None for g in games.values())
    assert all(g.is_primetime is False for g in games.values())


def test_week_with_varied_gametimes_kept_as_real(db):
    """A week with genuinely distinct kickoff times must not be flagged as a placeholder."""
    schedules = pd.DataFrame([
        _row("2026_03_A", 2026, 3, "2026-09-24", "13:00", "KC", "BUF"),
        _row("2026_03_B", 2026, 3, "2026-09-24", "16:25", "PHI", "DAL"),
        _row("2026_03_C", 2026, 3, "2026-09-24", "20:20", "DAL", "KC"),
    ])
    upsert_games(db, schedules)
    games = {
        g.game_id: g for g in db.query(Game).filter(
            Game.sport == SPORT_NFL, Game.season == 2026, Game.week == 3
        )
    }
    assert len(games) == 3
    assert all(g.kickoff_time is not None for g in games.values())


def test_two_games_sharing_a_time_not_flagged_as_placeholder(db):
    """Threshold is more than 2 games — a bye-heavy week with only two games
    sharing a time by coincidence must not be treated as TBD."""
    schedules = pd.DataFrame([
        _row("2026_17_A", 2026, 17, "2027-01-03", "13:00", "KC", "BUF"),
        _row("2026_17_B", 2026, 17, "2027-01-03", "13:00", "PHI", "DAL"),
    ])
    upsert_games(db, schedules)
    games = {
        g.game_id: g for g in db.query(Game).filter(
            Game.sport == SPORT_NFL, Game.season == 2026, Game.week == 17
        )
    }
    assert len(games) == 2
    assert all(g.kickoff_time is not None for g in games.values())


def test_kickoff_utc_returns_none_for_missing_gametime():
    """A single row with no gametime at all is a narrower, per-row unknown —
    must not default to a fake 13:00 kickoff either."""
    assert _kickoff_utc("2026-09-17", None) is None


def test_kickoff_utc_computes_real_time_when_known():
    kickoff = _kickoff_utc("2026-09-17", "16:25")
    assert kickoff is not None


def test_status_final_only_when_both_scores_exist(db):
    """Completion invariant: one score alone does not make a game final."""
    half = _row("2026_04_A", 2026, 4, "2026-10-01", "13:00", "KC", "BUF")
    half["home_score"] = 21
    both = _row("2026_04_B", 2026, 4, "2026-10-01", "16:25", "PHI", "DAL")
    both["home_score"], both["away_score"] = 21, 17
    upsert_games(db, pd.DataFrame([half, both]))
    rows = db.query(Game).filter(Game.season == 2026, Game.week == 4)
    status = {g.game_id: g.status for g in rows}
    assert status == {"2026_04_A": "scheduled", "2026_04_B": "final"}


def _playoff(game_id, game_type, week, home, away, location="Home", stadium=None):
    row = _row(game_id, 2026, week, "2027-01-17", "16:30", home, away)
    row.update(game_type=game_type, location=location, stadium=stadium)
    return row


def test_wild_card_row_gets_round_and_event(db):
    """PS-N1: a WC row is a postseason wild_card game. PS-N2: named for the home conference."""
    upsert_games(db, pd.DataFrame([_playoff("2026_19_BUF_KC", "WC", 19, "KC", "BUF")]))
    game = db.get(Game, "2026_19_BUF_KC")
    assert (game.season_type, game.round, game.event_name) == (
        "postseason", "wild_card", "AFC Wild Card")


def test_regular_row_without_game_type_stays_regular(db):
    """PS-N1: rows with no game_type (or REG) are regular season with no round."""
    upsert_games(db, pd.DataFrame([_row("2026_05_BUF_KC", 2026, 5, "2026-10-11", "13:00")]))
    game = db.get(Game, "2026_05_BUF_KC")
    assert (game.season_type, game.round, game.event_name) == ("regular", None, None)


def test_super_bowl_is_neutral_and_named(db):
    """PS-N2: Super Bowl LXI for 2026. PS-N3: a known neutral venue links its stadium."""
    from app.models import Stadium

    sofi = Stadium(name="SoFi Stadium", city="Inglewood", lat=33.95, lon=-118.34,
                   is_dome=True, surface="turf")
    db.add(sofi)
    db.flush()
    row = _playoff("2026_22_KC_PHI", "SB", 22, "PHI", "KC", "Neutral", "SoFi Stadium")
    upsert_games(db, pd.DataFrame([row]))
    game = db.get(Game, "2026_22_KC_PHI")
    assert game.is_neutral_site is True
    assert game.venue_name == "SoFi Stadium"
    assert game.stadium_id == sofi.stadium_id
    assert (game.round, game.event_name) == ("super_bowl", "Super Bowl LXI")


def test_neutral_game_with_unknown_stadium_keeps_null_stadium(db):
    """PS-N3: an unmatched neutral venue keeps stadium_id NULL and its raw name."""
    row = _playoff("2026_22_KC_PHI", "SB", 22, "PHI", "KC", "Neutral", "Nowhere Field")
    upsert_games(db, pd.DataFrame([row]))
    game = db.get(Game, "2026_22_KC_PHI")
    assert game.stadium_id is None and game.venue_name == "Nowhere Field"


def test_unresolvable_team_row_is_skipped_not_fatal(db, capsys):
    """PS-N4: one bad team row is logged and skipped; the others load."""
    rows = [
        _row("2026_05_BUF_KC", 2026, 5, "2026-10-11", "13:00"),
        _row("2026_05_TBD_KC", 2026, 5, "2026-10-11", "16:25", "KC", "TBD"),
        _row("2026_05_DAL_PHI", 2026, 5, "2026-10-11", "20:20", "PHI", "DAL"),
    ]
    assert upsert_games(db, pd.DataFrame(rows)) == 2
    assert db.get(Game, "2026_05_TBD_KC") is None
    assert "skipped NFL row 2026_05_TBD_KC" in capsys.readouterr().out


def test_missing_gameday_row_is_skipped(db, capsys):
    """PS-N4: a row without a gameday is skipped, not fatal."""
    rows = [
        _row("2026_05_BUF_KC", 2026, 5, None, None),
        _row("2026_05_DAL_PHI", 2026, 5, "2026-10-11", "20:20", "PHI", "DAL"),
    ]
    assert upsert_games(db, pd.DataFrame(rows)) == 1
    assert "skipped NFL row 2026_05_BUF_KC" in capsys.readouterr().out


def test_unknown_game_type_row_is_skipped(db, capsys):
    """PS-N1: a row with an unknown game_type (e.g. a Pro Bowl) is skipped and logged."""
    rows = [
        _playoff("2026_23_AFC_NFC", "PRO", 23, "KC", "PHI"),
        _playoff("2026_19_BUF_KC", "WC", 19, "KC", "BUF"),
    ]
    assert upsert_games(db, pd.DataFrame(rows)) == 1
    assert db.get(Game, "2026_23_AFC_NFC") is None
    assert "skipped NFL row 2026_23_AFC_NFC" in capsys.readouterr().out
