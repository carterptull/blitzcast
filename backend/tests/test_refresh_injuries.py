from datetime import UTC, date, datetime, timedelta

from app.models import SPORT_NFL, Game, Team
from data_pipeline.refresh_injuries import _next_game_by_team


def _teams(db):
    return {t.abbr: t.team_id for t in db.query(Team).filter(Team.sport == SPORT_NFL)}


def test_tbd_kickoff_game_receives_injuries(db):
    """PS-O4: a team whose next game has no kickoff time yet still gets it as its next game."""
    t = _teams(db)
    soon = date.today() + timedelta(days=3)
    db.add(Game(game_id="2030_19_BUF_KC", season=2030, week=19, game_date=soon,
                kickoff_time=None, home_team_id=t["KC"], away_team_id=t["BUF"]))
    db.commit()
    nxt = _next_game_by_team(db, 2030)
    assert nxt[t["KC"]] == "2030_19_BUF_KC" and nxt[t["BUF"]] == "2030_19_BUF_KC"


def test_dated_earlier_game_beats_later_tbd_game(db):
    """PS-O4: a dated game sooner than a TBD-time game stays the team's next game."""
    t = _teams(db)
    db.add(Game(game_id="2030_18_DAL_KC", season=2030, week=18,
                game_date=date.today() + timedelta(days=1),
                kickoff_time=datetime.now(UTC) + timedelta(days=1),
                home_team_id=t["KC"], away_team_id=t["DAL"]))
    db.add(Game(game_id="2030_19_BUF_KC", season=2030, week=19,
                game_date=date.today() + timedelta(days=8), kickoff_time=None,
                home_team_id=t["KC"], away_team_id=t["BUF"]))
    db.commit()
    assert _next_game_by_team(db, 2030)[t["KC"]] == "2030_18_DAL_KC"


def test_past_tbd_game_is_ignored(db):
    """PS-O4: a TBD-time game whose date has passed is not anyone's next game."""
    t = _teams(db)
    db.add(Game(game_id="2030_01_BUF_KC", season=2030, week=1,
                game_date=date.today() - timedelta(days=2), kickoff_time=None,
                home_team_id=t["KC"], away_team_id=t["BUF"]))
    db.commit()
    assert t["KC"] not in _next_game_by_team(db, 2030)
