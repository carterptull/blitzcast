"""CFB postseason ingestion, checked against real 2025 CFBD rows (Phase 0 fixtures)."""

import json
import re
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import SPORT_CFB, Base, Game, Team
from app.postseason import CFB_POSTSEASON_WEEK
from data_pipeline.cfb_games_loader import upsert_games

FIXTURES = Path(__file__).parent / "fixtures"


def _rows(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _frame(rows: list[dict]) -> pd.DataFrame:
    # Same flattening as cfbd.load_games.
    return pd.json_normalize(rows)


@pytest.fixture()
def pdb():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    seen: dict[str, str] = {}
    for row in _rows("cfbd_post_2025.json") + _rows("cfbd_reg_2025_w15.json"):
        for side in ("home", "away"):
            cls = row.get(f"{side}Classification")
            if cls in ("fbs", "fcs"):
                seen.setdefault(row[f"{side}Team"], cls)
    for i, (school, cls) in enumerate(sorted(seen.items())):
        conference = next(
            (r.get("homeConference") if r["homeTeam"] == school else r.get("awayConference"))
            for r in _rows("cfbd_post_2025.json") + _rows("cfbd_reg_2025_w15.json")
            if school in (r["homeTeam"], r["awayTeam"])
        ) or "Independent"
        session.add(Team(sport=SPORT_CFB, abbr=f"T{i}", name=school,
                         conference=conference, tier=cls.upper()))
    session.flush()
    yield session
    session.close()
    engine.dispose()


def _games(db) -> list[Game]:
    return list(db.scalars(select(Game)))


def test_real_2025_postseason_fixture_loads_46_fbs_games(pdb):
    """PS-C11: the real 2025 postseason loads exactly the 46 FBS games at slate week 17."""
    upsert_games(pdb, _frame(_rows("cfbd_post_2025.json")))
    games = _games(pdb)
    assert len(games) == 46
    assert {g.week for g in games} == {CFB_POSTSEASON_WEEK}
    assert {g.season_type for g in games} == {"postseason"}
    cfp = [g for g in games if g.round and g.round.startswith("cfp_")]
    assert len(cfp) == 11
    assert all(g.home_seed and g.away_seed for g in cfp)
    first_round = [g for g in cfp if g.round == "cfp_first_round"]
    assert len(first_round) == 4 and not any(g.is_neutral_site for g in first_round)
    hawaii = next(g for g in games if g.event_name == "Sheraton Hawai'i Bowl")
    assert hawaii.is_neutral_site is False
    assert all("–" not in g.event_name and "—" not in g.event_name for g in games)


def test_postseason_bowl_stored_at_slate_week_17(pdb):
    """PS-C2: a non-CFP bowl is postseason, week 17, round bowl, named from notes."""
    upsert_games(pdb, _frame(_rows("cfbd_post_2025.json")))
    pinstripe = next(g for g in _games(pdb) if g.event_name == "Bad Boy Mowers Pinstripe Bowl")
    assert (pinstripe.season_type, pinstripe.week, pinstripe.round) == (
        "postseason", 17, "bowl")
    assert pinstripe.home_seed is None and pinstripe.away_seed is None


def test_cfp_game_gets_round_and_seeds(pdb):
    """PS-C2: a CFP quarterfinal keeps its round, bowl and both seeds."""
    upsert_games(pdb, _frame(_rows("cfbd_post_2025.json")))
    rose = next(g for g in _games(pdb) if g.event_name == "Rose Bowl, CFP Quarterfinal")
    assert rose.round == "cfp_quarterfinal"
    assert (rose.home_seed, rose.away_seed) == (1, 9)
    assert rose.is_neutral_site is True
    title = next(g for g in _games(pdb) if g.round == "cfp_championship")
    assert title.event_name == "CFP National Championship"


def _one_cfp_row(**changes) -> list[dict]:
    row = next(r for r in _rows("cfbd_post_2025.json")
               if (r.get("playoff") or {}).get("round") == "quarterfinal")
    row = json.loads(json.dumps(row))
    for key, value in changes.items():
        row[key] = value
    return [row]


def test_unknown_playoff_round_is_cfp_other(pdb, capsys):
    """PS-C3: an unknown CFBD playoff round is stored as cfp_other, never dropped."""
    rows = _one_cfp_row()
    rows[0]["playoff"]["round"] = "second_round"
    rows[0]["playoff"]["bowlName"] = None
    upsert_games(pdb, _frame(rows))
    (game,) = _games(pdb)
    assert (game.round, game.event_name) == ("cfp_other", "College Football Playoff")
    assert "second_round" in capsys.readouterr().out


def test_postseason_row_without_playoff_object_is_a_bowl(pdb):
    """PS-C2: a postseason row with no playoff object and junk notes is a generic bowl."""
    rows = _one_cfp_row(playoff=None, notes="Visit http://bowl.example")
    upsert_games(pdb, _frame(rows))
    (game,) = _games(pdb)
    assert (game.round, game.event_name, game.week) == ("bowl", "Bowl game", 17)


def test_postseason_upsert_overwrites_kickoff_venue_and_event(pdb):
    """PS-C4: Selection Day changes to time, venue, neutral flag, bowl and seeds overwrite."""
    upsert_games(pdb, _frame(_one_cfp_row()))
    rows = _one_cfp_row(startDate="2026-01-01T17:00:00.000Z", venue="AT&T Stadium",
                        neutralSite=False)
    rows[0]["playoff"].update(bowlName="Cotton Bowl", homeSeed=2, awaySeed=7)
    upsert_games(pdb, _frame(rows))
    (game,) = _games(pdb)
    assert game.kickoff_time.isoformat().startswith("2026-01-01T17:00")
    assert game.is_neutral_site is False
    assert game.event_name == "Cotton Bowl, CFP Quarterfinal"
    assert (game.home_seed, game.away_seed) == (2, 7)
    assert game.venue_name == "AT&T Stadium" or game.stadium_id is not None


def test_fcs_postseason_rows_skipped(pdb):
    """PS-C1: FCS, D-II and D-III postseason rows (Celebration Bowl, playoffs) are skipped."""
    rows = [r for r in _rows("cfbd_post_2025.json") if r["homeClassification"] != "fbs"]
    assert len(rows) == 3
    written, skipped = upsert_games(pdb, _frame(rows))
    assert written == 0 and skipped == 3


def test_postseason_fbs_vs_fcs_row_skipped(pdb):
    """PS-C1: a postseason row is kept only when both sides are FBS."""
    rows = _one_cfp_row(awayClassification="fcs")
    written, skipped = upsert_games(pdb, _frame(rows))
    assert (written, skipped) == (0, 1)


def test_real_2025_championships_tagged(pdb):
    """PS-C6: all 9 real 2025 title games are tagged conf_championship and named."""
    upsert_games(pdb, _frame(_rows("cfbd_reg_2025_w15.json")))
    games = _games(pdb)
    assert len(games) == 9
    assert {g.round for g in games} == {"conf_championship"}
    assert {g.season_type for g in games} == {"regular"}
    assert "SEC Championship" in {g.event_name for g in games}
    assert all(g.week == 15 for g in games)


def test_championship_without_signal_still_loads(pdb):
    """PS-C7: a title game whose notes are missing still loads, just without the label."""
    row = json.loads(json.dumps(_rows("cfbd_reg_2025_w15.json")[0]))
    row["notes"] = None
    upsert_games(pdb, _frame([row]))
    (game,) = _games(pdb)
    assert game.round is None and game.event_name is None and game.week == 15


def test_regular_week_at_or_above_postseason_slate_week_is_rejected(pdb, capsys):
    """PS-C8: a regular-season row at week 17+ is logged and skipped."""
    row = json.loads(json.dumps(_rows("cfbd_reg_2025_w15.json")[0]))
    row["week"] = 17
    written, skipped = upsert_games(pdb, _frame([row]))
    assert (written, skipped) == (0, 1)
    assert "week 17" in capsys.readouterr().out


def test_refresh_schedule_fetches_regular_and_postseason(monkeypatch):
    """PS-C1: the schedule sync asks CFBD for regular and FBS postseason games."""
    from data_pipeline import refresh_schedule_cfb

    calls = []

    def fake_load_games(year, season_type="regular", classification=None):
        calls.append((season_type, classification))
        return pd.DataFrame()

    monkeypatch.setattr(refresh_schedule_cfb.cfbd, "load_games", fake_load_games)
    monkeypatch.setattr(refresh_schedule_cfb.get_settings(), "cfbd_api_key", "k")
    monkeypatch.setattr("sys.argv", ["refresh_schedule_cfb", "--season", "2026"])
    refresh_schedule_cfb.main()
    assert ("regular", None) in calls and ("postseason", "fbs") in calls


def test_load_rankings_only_ever_regular():
    """PS-C10: no pipeline code asks CFBD for postseason rankings (the final poll leaks)."""
    root = Path(__file__).resolve().parents[1] / "data_pipeline"
    calls = []
    for path in root.rglob("*.py"):
        calls += re.findall(r"load_rankings\(([^)]*)\)", path.read_text(encoding="utf-8"))
    calls = [c for c in calls if not c.startswith("year: int")]
    assert calls, "expected at least one load_rankings call"
    assert all("postseason" not in c and "both" not in c for c in calls)


def test_stats_refresh_includes_postseason_games(monkeypatch, db):
    """PS-C9: the in-season stats refresh pulls postseason PPA as well as regular."""
    from data_pipeline import backfill_cfb

    asked = []

    def fake_ppa(year, season_type="regular"):
        asked.append(season_type)
        return pd.DataFrame()

    monkeypatch.setattr(backfill_cfb.cfbd, "load_team_game_ppa", fake_ppa)
    backfill_cfb.backfill_team_game_stats(db, 2026, season_types=("regular", "postseason"))
    assert asked == ["regular", "postseason"]
    asked.clear()
    backfill_cfb.backfill_team_game_stats(db, 2026)
    assert asked == ["regular"]


def test_refresh_stats_requests_postseason(monkeypatch):
    """PS-C9: refresh_stats_cfb passes both season types to the stats backfill."""
    from data_pipeline import refresh_stats_cfb

    seen = {}

    def fake_backfill(db, season, season_types=("regular",)):
        seen["types"] = season_types
        return 0

    monkeypatch.setattr(refresh_stats_cfb, "backfill_team_game_stats", fake_backfill)
    monkeypatch.setattr(refresh_stats_cfb, "has_final_games", lambda *_: True)
    monkeypatch.setattr(refresh_stats_cfb.get_settings(), "cfbd_api_key", "k")
    monkeypatch.setattr(refresh_stats_cfb, "session_scope", _null_scope)
    monkeypatch.setattr("sys.argv", ["refresh_stats_cfb", "--season", "2026"])
    refresh_stats_cfb.main()
    assert seen["types"] == ("regular", "postseason")


class _null_scope:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


@pytest.mark.parametrize("bad", ["first", 0, -3, 99, 40000, 5.5])
def test_out_of_range_or_bad_seeds_are_dropped(pdb, bad):
    """PS-C2: only whole-number seeds 1-16 are stored; anything else is dropped, not fatal."""
    rows = _one_cfp_row()
    rows[0]["playoff"]["homeSeed"] = bad
    written, _ = upsert_games(pdb, _frame(rows))
    (game,) = _games(pdb)
    assert written == 1 and game.home_seed is None
    assert game.away_seed == rows[0]["playoff"]["awaySeed"]


def test_one_malformed_row_does_not_abort_the_sync(pdb, capsys):
    """PS-C4: a malformed row is logged and skipped; the rest of the sync still loads."""
    good = _rows("cfbd_post_2025.json")[:3]
    bad = json.loads(json.dumps(good[0]))
    bad["id"] = "not-a-number"
    written, skipped = upsert_games(pdb, _frame([bad] + good[1:]))
    assert written == 2 and skipped == 1
    assert "skipping cfb game" in capsys.readouterr().out
