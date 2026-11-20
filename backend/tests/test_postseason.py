from pathlib import Path

import pytest

from app.postseason import (
    CFB_POSTSEASON_WEEK,
    NFL_GAME_TYPES,
    ROUND_LABELS,
    ROUND_SLUGS,
    ROUNDS,
    SEASON_POSTSEASON,
    SEASON_REGULAR,
    cfb_playoff_round,
    cfp_event_name,
    clean_event_name,
    generic_event_name,
    is_conf_championship,
    nfl_event_name,
    nfl_round,
    round_for_slug,
    super_bowl_name,
)


def test_constants_match_spec_appendix_b():
    """PS-D5: rounds, slugs, labels and the slate week are defined once, as in Appendix B."""
    assert SEASON_REGULAR == "regular" and SEASON_POSTSEASON == "postseason"
    assert CFB_POSTSEASON_WEEK == 17
    assert NFL_GAME_TYPES == ("REG", "WC", "DIV", "CON", "SB")
    assert ROUNDS == (
        "conf_championship", "wild_card", "divisional", "conference", "super_bowl", "bowl",
        "cfp_first_round", "cfp_quarterfinal", "cfp_semifinal", "cfp_championship", "cfp_other",
    )
    assert ROUND_SLUGS == {
        "wild_card": "wild-card", "divisional": "divisional", "conference": "conference",
        "super_bowl": "super-bowl", "bowl": "bowls", "cfp_first_round": "cfp-first-round",
        "cfp_quarterfinal": "cfp-quarterfinals", "cfp_semifinal": "cfp-semifinals",
        "cfp_championship": "cfp-title", "cfp_other": "cfp-other",
    }
    assert ROUND_LABELS["wild_card"] == ("Wild Card", "Round", "WC")
    assert ROUND_LABELS["bowl"] == ("Bowl Season", "Non-CFP", "Bowls")
    assert ROUND_LABELS["cfp_quarterfinal"] == ("CFP Quarterfinals", "CFP", "QF")
    assert ROUND_LABELS["cfp_championship"] == ("National Championship", "CFP", "Title")
    assert ROUND_LABELS["conf_championship"] == ("Conference Championships", "Champ", None)
    assert set(ROUND_LABELS) == set(ROUNDS)


def test_round_rules_live_only_in_postseason_module():
    """PS-D4: no other backend module maps feed round codes to rounds."""
    backend = Path(__file__).resolve().parents[1]
    offenders = []
    for folder in ("app", "data_pipeline", "ml"):
        for path in (backend / folder).rglob("*.py"):
            if path.name == "postseason.py":
                continue
            text = path.read_text(encoding="utf-8")
            if '"first_round"' in text or '"quarterfinal"' in text or '"DIV"' in text:
                offenders.append(str(path.relative_to(backend)))
    assert not offenders


def test_nfl_round_maps_game_types():
    """PS-D4: nflverse game types map to season type and round."""
    assert nfl_round("REG") == ("regular", None)
    assert nfl_round("WC") == ("postseason", "wild_card")
    assert nfl_round("DIV") == ("postseason", "divisional")
    assert nfl_round("CON") == ("postseason", "conference")
    assert nfl_round("SB") == ("postseason", "super_bowl")
    with pytest.raises(ValueError):
        nfl_round("PRO")


def test_super_bowl_name_2026_is_lxi():
    """PS-C5: the Super Bowl numeral is season minus 1965."""
    assert super_bowl_name(2026) == "Super Bowl LXI"
    assert super_bowl_name(2025) == "Super Bowl LX"
    assert super_bowl_name(2024) == "Super Bowl LIX"


def test_nfl_event_names():
    """PS-C5: NFL event names come from the round and the home team's conference."""
    assert nfl_event_name("wild_card", "AFC", 2026) == "AFC Wild Card"
    assert nfl_event_name("divisional", "NFC", 2026) == "NFC Divisional"
    assert nfl_event_name("conference", "NFC", 2026) == "NFC Championship"
    assert nfl_event_name("super_bowl", "NFC", 2026) == "Super Bowl LXI"


def test_cfb_playoff_round_maps_known_and_unknown():
    """PS-C5: CFBD playoff rounds map to ours; unknown ones become cfp_other."""
    assert cfb_playoff_round("first_round") == "cfp_first_round"
    assert cfb_playoff_round("quarterfinal") == "cfp_quarterfinal"
    assert cfb_playoff_round("semifinal") == "cfp_semifinal"
    assert cfb_playoff_round("championship") == "cfp_championship"
    assert cfb_playoff_round("second_round") == "cfp_other"
    assert cfb_playoff_round(None) == "cfp_other"


def test_clean_event_name_strips_dashes_and_sponsor_tails():
    """PS-C5: dashes become a comma, sponsor tails are dropped, hyphens and apostrophes stay."""
    expected = "Rose Bowl Game, CFP Quarterfinal"
    assert clean_event_name("Rose Bowl Game – CFP Quarterfinal") == expected
    assert clean_event_name("Rose Bowl Game—CFP Quarterfinal") == expected
    assert clean_event_name("Pop-Tarts Bowl presented by Kellogg") == "Pop-Tarts Bowl"
    assert clean_event_name("Duke's Mayo Bowl") == "Duke's Mayo Bowl"
    assert clean_event_name("68 Ventures Bowl") == "68 Ventures Bowl"


def test_clean_event_name_real_2025_notes():
    """PS-C5: real 2025 CFBD notes survive cleaning (okina becomes an apostrophe)."""
    assert clean_event_name("Sheraton Hawaiʻi Bowl") == "Sheraton Hawai'i Bowl"
    assert clean_event_name("IS4S Salute to Veterans Bowl") == "IS4S Salute to Veterans Bowl"
    assert (
        clean_event_name("Radiance Technologies Independence Bowl")
        == "Radiance Technologies Independence Bowl"
    )
    assert clean_event_name("SEC Championship") == "SEC Championship"


def test_clean_event_name_rejects_junk():
    """PS-C5: junk, links, ads and digit runs are rejected."""
    assert clean_event_name("Bowl 2026-27 Game 12345") is None
    assert clean_event_name("x" * 60) is None
    assert clean_event_name(None) is None
    assert clean_event_name("Visit http://x.y") is None
    assert clean_event_name("  ") is None


def test_cfp_event_name_uses_bowl_only_when_it_is_a_bowl():
    """PS-C5: CFP games use the bowl name only when it is a real bowl."""
    assert cfp_event_name("quarterfinal", "Cotton Bowl") == "Cotton Bowl, CFP Quarterfinal"
    assert cfp_event_name("semifinal", "Orange Bowl") == "Orange Bowl, CFP Semifinal"
    assert (
        cfp_event_name("first_round", "College Football Playoff First Round Game")
        == "CFP First Round"
    )
    assert (
        cfp_event_name(
            "championship", "College Football Playoff National Championship Presented by AT&T"
        )
        == "CFP National Championship"
    )
    assert cfp_event_name("second_round", None) == "College Football Playoff"


def test_generic_event_names():
    """PS-C5: every round has a generic fallback name."""
    assert generic_event_name("bowl") == "Bowl game"
    assert generic_event_name("cfp_first_round") == "CFP First Round"
    assert generic_event_name("cfp_quarterfinal") == "CFP Quarterfinal"
    assert generic_event_name("cfp_championship") == "CFP National Championship"
    assert generic_event_name("cfp_other") == "College Football Playoff"
    for r in ROUNDS:
        assert generic_event_name(r)


def test_is_conf_championship():
    """PS-C5: a title game is a championship note between two same-conference teams."""
    assert is_conf_championship("SEC Championship", "SEC", "SEC")
    assert is_conf_championship("american championship", "American Athletic", "American Athletic")
    assert not is_conf_championship("SEC Championship", "SEC", "Big Ten")
    assert not is_conf_championship(None, "SEC", "SEC")
    assert not is_conf_championship("SEC Championship", None, None)


def test_slugs_round_trip():
    """PS-D5: every postseason slug maps back to its round; unknown slugs do not."""
    for r, slug in ROUND_SLUGS.items():
        assert round_for_slug(slug) == r
    assert round_for_slug("bogus") is None
    assert "conf_championship" not in ROUND_SLUGS


def test_no_label_or_generic_name_contains_a_dash():
    """PS-C5: no label or generic name contains an en or em dash."""
    texts = [t for labels in ROUND_LABELS.values() for t in labels if t]
    texts += [generic_event_name(r) for r in ROUNDS]
    for text in texts:
        assert "–" not in text and "—" not in text


def _any_game_teams(db):
    from app.models import SPORT_NFL, Team

    teams = db.query(Team).filter(Team.sport == SPORT_NFL).limit(2).all()
    return teams[0].team_id, teams[1].team_id


def test_game_defaults_to_regular_season(db):
    """PS-D1: a new game is regular season with no round, event or seeds."""
    from datetime import date

    from app.models import Game

    home, away = _any_game_teams(db)
    db.add(Game(game_id="t_default", season=2026, week=3, game_date=date(2026, 9, 20),
                home_team_id=home, away_team_id=away))
    db.commit()
    g = db.get(Game, "t_default")
    assert g.season_type == "regular"
    assert g.round is None and g.event_name is None
    assert g.home_seed is None and g.away_seed is None


@pytest.mark.parametrize("field,value", [("round", "bogus"), ("season_type", "playoffs")])
def test_round_check_rejects_unknown_value(db, field, value):
    """PS-D2: the database rejects an unknown round or season type."""
    from datetime import date

    from sqlalchemy.exc import IntegrityError

    from app.models import Game

    home, away = _any_game_teams(db)
    db.add(Game(game_id="t_bad", season=2026, week=3, game_date=date(2026, 9, 20),
                home_team_id=home, away_team_id=away, **{field: value}))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def _migration():
    import importlib.util

    path = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
            / "d5a1c7e3f9b2_add_game_postseason_fields.py")
    spec = importlib.util.spec_from_file_location("postseason_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_backfills_nfl_history(db):
    """PS-D3: NFL history becomes postseason by week, with old and new numbering."""
    from datetime import date

    from sqlalchemy import text

    from app.models import SPORT_CFB, Game, Team

    home, away = _any_game_teams(db)
    cfb = [t.team_id for t in db.query(Team).filter(Team.sport == SPORT_CFB).limit(2)]
    rows = [
        ("n25_18", "NFL", 2025, 18), ("n25_19", "NFL", 2025, 19), ("n25_20", "NFL", 2025, 20),
        ("n25_21", "NFL", 2025, 21), ("n25_22", "NFL", 2025, 22),
        ("n20_17", "NFL", 2020, 17), ("n20_18", "NFL", 2020, 18), ("n20_21", "NFL", 2020, 21),
        ("c25_19", "CFB", 2025, 19),
    ]
    for gid, sport, season, week in rows:
        h, a = (cfb[0], cfb[1]) if sport == "CFB" else (home, away)
        db.add(Game(game_id=gid, sport=sport, season=season, week=week,
                    game_date=date(season, 12, 1), home_team_id=h, away_team_id=a))
    db.commit()

    for statement in _migration().backfill_statements(seasons=[2020, 2025]):
        db.execute(text(statement))
    db.commit()

    def got(gid):
        g = db.execute(text("SELECT season_type, round, event_name FROM games WHERE game_id=:g"),
                       {"g": gid}).one()
        return tuple(g)

    assert got("n25_18") == ("regular", None, None)
    assert got("n25_19") == ("postseason", "wild_card", None)
    assert got("n25_20") == ("postseason", "divisional", None)
    assert got("n25_21") == ("postseason", "conference", None)
    assert got("n25_22") == ("postseason", "super_bowl", "Super Bowl LX")
    assert got("n20_17") == ("regular", None, None)
    assert got("n20_18") == ("postseason", "wild_card", None)
    assert got("n20_21") == ("postseason", "super_bowl", "Super Bowl LV")
    assert got("c25_19") == ("regular", None, None)
