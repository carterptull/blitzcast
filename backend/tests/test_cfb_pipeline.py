"""CFB pipeline tests: the FCS-vs-FCS skip chokepoint, the data-driven name
resolver, and the CFBD loaders. Self-contained — no network, no shared
fixtures."""

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import SPORT_CFB, Base, Game, PollRank, Team
from data_pipeline.backfill_cfb import pick_lines
from data_pipeline.cfb_games_loader import should_skip_game, upsert_games
from data_pipeline.cfb_team_names import build_alias_map, cfb_to_abbr, derive_abbrs
from data_pipeline.refresh_polls_cfb import upsert_polls
from data_pipeline.seed_cfb import espn_id_from_logo

TEAMS_DF = pd.DataFrame(
    [
        {"school": "Ohio State", "mascot": "Buckeyes", "abbreviation": "OSU",
         "alternateNames": ["Ohio St."]},
        {"school": "Miami", "mascot": "Hurricanes", "abbreviation": "MIA",
         "alternateNames": ["Miami (FL)"]},
        {"school": "Miami (OH)", "mascot": "RedHawks", "abbreviation": "M-OH",
         "alternateNames": []},
        {"school": "North Dakota State", "mascot": "Bison", "abbreviation": "NDSU",
         "alternateNames": None},
    ]
)


@pytest.fixture()
def aliases():
    return build_alias_map(TEAMS_DF)


# --- FCS-vs-FCS skip chokepoint ---


def test_both_fcs_skipped():
    assert should_skip_game("FCS", "FCS") is True


def test_fbs_vs_fcs_kept():
    assert should_skip_game("FBS", "FCS") is False
    assert should_skip_game("FCS", "FBS") is False
    assert should_skip_game("FBS", "FBS") is False


def test_unknown_team_skipped():
    assert should_skip_game(None, "FBS") is True
    assert should_skip_game("FBS", None) is True
    assert should_skip_game(None, None) is True


# --- name resolver ---


def test_cfbd_school_names(aliases):
    assert cfb_to_abbr("Ohio State", aliases) == "OSU"
    assert cfb_to_abbr("Miami (OH)", aliases) == "M-OH"


def test_odds_api_display_names(aliases):
    assert cfb_to_abbr("Ohio State Buckeyes", aliases) == "OSU"
    assert cfb_to_abbr("Miami Hurricanes", aliases) == "MIA"
    assert cfb_to_abbr("Miami (OH) RedHawks", aliases) == "M-OH"


def test_alternate_names_and_abbrs(aliases):
    assert cfb_to_abbr("Ohio St.", aliases) == "OSU"
    assert cfb_to_abbr("Miami (FL)", aliases) == "MIA"
    assert cfb_to_abbr("NDSU", aliases) == "NDSU"


def test_prefix_fallback(aliases):
    assert cfb_to_abbr("North Dakota State University", aliases) == "NDSU"


def test_unmatched_name_raises(aliases):
    with pytest.raises(KeyError):
        cfb_to_abbr("Springfield Atoms", aliases)
    with pytest.raises(ValueError):
        cfb_to_abbr("", aliases)


def test_ambiguous_alias_dropped():
    df = pd.DataFrame(
        [
            {"school": "Alpha", "mascot": "Tigers", "abbreviation": "ALP",
             "alternateNames": ["The U"]},
            {"school": "Beta", "mascot": "Tigers", "abbreviation": "BET",
             "alternateNames": ["The U"]},
        ]
    )
    table = build_alias_map(df)
    assert table["alpha"] == "ALP"
    assert table["beta"] == "BET"
    with pytest.raises(KeyError):
        cfb_to_abbr("The U", table)


def test_derive_abbrs_decollides():
    df = pd.DataFrame(
        [
            {"school": "Ohio State", "abbreviation": "OSU"},
            {"school": "Oregon State", "abbreviation": "OSU"},
            {"school": "Sam Houston", "abbreviation": None},
        ]
    )
    abbrs = derive_abbrs(df)
    assert abbrs["Ohio State"] == "OSU"
    assert abbrs["Oregon State"] != "OSU"
    assert abbrs["Sam Houston"]
    assert len(set(abbrs.values())) == 3


# --- seed helpers ---


def test_espn_id_from_logo():
    assert espn_id_from_logo("http://a.espncdn.com/i/teamlogos/ncaa/500/194.png") == 194
    assert espn_id_from_logo(None) is None
    assert espn_id_from_logo("https://example.com/logo.svg") is None


# --- betting line provider selection ---


def test_pick_lines_prefers_consensus_then_bovada():
    lines = pd.DataFrame(
        [
            {"game_id": 1, "provider": "teamrankings", "spread": -3.0,
             "over_under": 50.0, "home_moneyline": -150, "away_moneyline": 130},
            {"game_id": 1, "provider": "Bovada", "spread": -3.5,
             "over_under": 51.0, "home_moneyline": -160, "away_moneyline": 140},
            {"game_id": 2, "provider": "consensus", "spread": 7.0,
             "over_under": 44.0, "home_moneyline": 220, "away_moneyline": -270},
            {"game_id": 2, "provider": "Bovada", "spread": 6.5,
             "over_under": 45.0, "home_moneyline": 210, "away_moneyline": -260},
            {"game_id": 3, "provider": "someBook", "spread": -1.0,
             "over_under": 60.0, "home_moneyline": -110, "away_moneyline": -110},
        ]
    )
    picked = pick_lines(lines).set_index("game_id")
    assert picked.loc[1, "provider"] == "Bovada"
    assert picked.loc[2, "provider"] == "consensus"
    assert picked.loc[3, "provider"] == "someBook"


# --- game upsert against an in-memory DB ---

GAMES_DF = pd.DataFrame(
    [
        # FBS vs FCS: kept (19:30 ET kickoff -> primetime).
        {"id": 101, "season": 2025, "week": 1, "startDate": "2025-08-30T23:30:00.000Z",
         "startTimeTBD": False, "completed": True, "conferenceGame": False,
         "venue": "The Horseshoe", "homeTeam": "Ohio State",
         "awayTeam": "North Dakota State", "homePoints": 42, "awayPoints": 3},
        # FCS vs FCS: skipped.
        {"id": 102, "season": 2025, "week": 1, "startDate": "2025-08-30T20:00:00.000Z",
         "startTimeTBD": False, "completed": True, "conferenceGame": False,
         "venue": None, "homeTeam": "North Dakota State", "awayTeam": "Montana",
         "homePoints": 21, "awayPoints": 14},
        # Unresolvable opponent: skipped.
        {"id": 103, "season": 2025, "week": 1, "startDate": "2025-08-30T16:00:00.000Z",
         "startTimeTBD": False, "completed": True, "conferenceGame": False,
         "venue": None, "homeTeam": "Michigan", "awayTeam": "Valdosta State",
         "homePoints": 35, "awayPoints": 0},
        # FBS vs FBS, kickoff TBD: kept with NULL kickoff.
        {"id": 104, "season": 2025, "week": 2, "startDate": "2025-09-06T04:00:00.000Z",
         "startTimeTBD": True, "completed": False, "conferenceGame": True,
         "venue": "The Horseshoe", "homeTeam": "Ohio State", "awayTeam": "Michigan",
         "homePoints": None, "awayPoints": None},
    ]
)


@pytest.fixture()
def cfb_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    for abbr, name, conf, tier in (
        ("OSU", "Ohio State", "Big Ten", "FBS"),
        ("MICH", "Michigan", "Big Ten", "FBS"),
        ("NDSU", "North Dakota State", "Missouri Valley", "FCS"),
        ("MONT", "Montana", "Big Sky", "FCS"),
    ):
        session.add(Team(sport=SPORT_CFB, abbr=abbr, name=name, conference=conf, tier=tier))
    session.flush()
    yield session
    session.close()
    engine.dispose()


def test_upsert_games_applies_scope_rule(cfb_db):
    written, skipped = upsert_games(cfb_db, GAMES_DF)
    assert written == 2 and skipped == 2
    ids = {g.game_id for g in cfb_db.scalars(select(Game))}
    assert ids == {"cfb_101", "cfb_104"}


def test_upsert_games_fields(cfb_db):
    upsert_games(cfb_db, GAMES_DF)
    played = cfb_db.get(Game, "cfb_101")
    assert played.sport == SPORT_CFB
    assert played.is_primetime is True
    assert played.is_divisional is False
    assert played.status == "final"
    assert (played.home_score, played.away_score) == (42, 3)

    tbd = cfb_db.get(Game, "cfb_104")
    assert tbd.kickoff_time is None
    assert tbd.game_date is not None
    assert tbd.is_primetime is False
    assert tbd.is_divisional is True
    assert tbd.status == "scheduled"


def test_upsert_games_idempotent_and_updates(cfb_db):
    upsert_games(cfb_db, GAMES_DF)
    updated = GAMES_DF.copy()
    updated.loc[updated["id"] == 104, "startTimeTBD"] = False
    upsert_games(cfb_db, updated)
    assert len(cfb_db.scalars(select(Game)).all()) == 2
    assert cfb_db.get(Game, "cfb_104").kickoff_time is not None


# --- poll upsert ---


def test_upsert_polls_prefers_ap_and_skips_unknown(cfb_db):
    rankings = pd.DataFrame(
        [
            {"season": 2025, "week": 1, "poll": "AP Top 25", "school": "Ohio State", "rank": 1},
            {"season": 2025, "week": 1, "poll": "AP Top 25", "school": "Nowhere U", "rank": 2},
            {"season": 2025, "week": 1, "poll": "Coaches Poll", "school": "Michigan", "rank": 1},
            {"season": 2025, "week": 2, "poll": "Coaches Poll", "school": "Michigan", "rank": 1},
        ]
    )
    n = upsert_polls(cfb_db, rankings)
    assert n == 2  # week 1 AP only (unknown skipped) + week 2 Coaches fallback
    rows = cfb_db.scalars(select(PollRank)).all()
    assert {(r.week, r.poll) for r in rows} == {(1, "AP Top 25"), (2, "Coaches Poll")}

    # Re-running is idempotent (delete-then-insert per season).
    assert upsert_polls(cfb_db, rankings) == 2
    assert len(cfb_db.scalars(select(PollRank)).all()) == 2
