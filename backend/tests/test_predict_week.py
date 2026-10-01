"""predict_week selection predicates and fact-sheet shaping."""

from datetime import UTC, date, datetime, timedelta

import pandas as pd
from sqlalchemy import select

from app.jobs.predict_week import default_week
from app.models import SPORT_CFB, SPORT_NFL, Game, Team


def test_default_week_is_sport_scoped(db):
    now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
    assert default_week(db, 2026, SPORT_NFL, now=now) == 1
    assert default_week(db, 2026, SPORT_CFB, now=now) == 1
    assert default_week(db, 2025, SPORT_NFL, now=now) is None  # all played
    assert default_week(db, 2025, SPORT_CFB, now=now) is None  # no CFB games that season


def test_null_kickoff_game_still_selected(db):
    """A scheduled game with a TBD (NULL) kickoff must not drop out of the
    target-week selection."""
    uga = db.query(Team).filter_by(sport=SPORT_CFB, abbr="UGA").one()
    mer = db.query(Team).filter_by(sport=SPORT_CFB, abbr="MER").one()
    db.add(
        Game(
            game_id="cfb_401900001",
            sport=SPORT_CFB, season=2027, week=5,
            game_date=date(2027, 10, 2), kickoff_time=None,
            home_team_id=uga.team_id, away_team_id=mer.team_id,
            status="scheduled",
        )
    )
    db.flush()
    now = datetime(2027, 10, 2, 12, 0, tzinfo=UTC)
    assert default_week(db, 2027, SPORT_CFB, now=now) == 5


def _row(game_id: str, **cols) -> pd.Series:
    return pd.Series({"game_id": game_id, "market_spread_home": 2.0, **cols})


def test_facts_for_row_hides_a_spread_with_no_posted_line(db):
    from app.jobs.predict_week import facts_for_row

    row = _row("2026_01_BUF_KC", market_spread_home=6.2, has_market_line=0.0,
               has_market_spread=0.0)
    facts = facts_for_row(db, row, 0.7, [], {}, {})
    assert facts.spread_home is None
    assert facts.total is None


def test_facts_for_row_hides_a_moneyline_derived_spread(db):
    from app.jobs.predict_week import facts_for_row

    row = _row("2026_01_BUF_KC", has_market_line=1.0, has_market_spread=0.0)
    assert facts_for_row(db, row, 0.6, [], {}, {}).spread_home is None


def test_facts_for_row_keeps_a_posted_spread(db):
    from app.jobs.predict_week import facts_for_row

    row = _row("2026_01_BUF_KC", has_market_line=1.0, has_market_spread=1.0)
    facts = facts_for_row(db, row, 0.6, [], {}, {})
    assert facts.spread_home == 2.0
    assert isinstance(facts.spread_home, float)


def test_facts_for_row_defaults_to_a_posted_spread_when_the_flag_is_absent(db):
    from app.jobs.predict_week import facts_for_row

    row = _row("2026_01_BUF_KC")
    assert facts_for_row(db, row, 0.6, [], {}, {}).spread_home == 2.0


def test_facts_for_row_nfl_carries_injuries_and_no_poll(db):
    from app.jobs.predict_week import facts_for_row

    facts = facts_for_row(db, _row("2026_01_BUF_KC", has_market_spread=1.0), 0.6, [], {}, {})
    assert facts.sport == SPORT_NFL
    assert facts.home.name == "Chiefs"
    assert facts.poll_available is False
    assert any("Test Quarterback" in i for i in facts.away.injuries)


def test_facts_for_row_cfb_is_poll_aware_with_no_injuries(db):
    from app.jobs.predict_week import facts_for_row

    ala = db.query(Team).filter_by(sport=SPORT_CFB, abbr="ALA").one()
    uga = db.query(Team).filter_by(sport=SPORT_CFB, abbr="UGA").one()
    row = _row("cfb_401800001", has_market_spread=1.0)
    facts = facts_for_row(
        db, row, 0.55, [],
        {ala.team_id: 7, uga.team_id: 3}, {ala.team_id: 9, uga.team_id: 3},
    )
    assert facts.sport == SPORT_CFB
    assert facts.poll_available is True
    assert (facts.home.rank, facts.away.rank) == (7, 3)
    assert facts.home.rank_note == "up from #9"
    assert facts.away.rank_note == "holding steady"
    assert facts.home.injuries == () and facts.away.injuries == ()


def test_facts_for_row_cfb_without_ranks_is_not_poll_aware(db):
    from app.jobs.predict_week import facts_for_row

    facts = facts_for_row(db, _row("cfb_401800002", has_market_spread=0.0), 0.97, [], {}, {})
    assert facts.poll_available is False
    assert facts.home.rank is None and facts.away.rank is None
    assert facts.spread_home is None


def test_build_features_carries_the_columns_predict_week_reads(db):
    from ml.features import build_features

    features = build_features(db, seasons=[2026], sport=SPORT_NFL)
    week = features[features["week"] == 1]
    assert not week.empty
    for col in ("game_id", "has_market_line", "has_market_spread", "market_spread_home"):
        assert col in week.columns
    row = week.iloc[0]
    assert bool(row["has_market_spread"]) and bool(row["has_market_line"])


def test_unplayed_game_ids_excludes_finished_games(db):
    """A finished game must not be re-predicted; that would overwrite the
    pre-game call and restamp predicted_at after the result was known."""
    from app.jobs.predict_week import unplayed_game_ids

    game = db.scalar(select(Game).where(Game.game_id == "2026_01_BUF_KC"))
    week = game.week
    before_kickoff = game.kickoff_time - timedelta(hours=1)
    assert "2026_01_BUF_KC" in unplayed_game_ids(
        db, 2026, week, SPORT_NFL, now=before_kickoff
    )

    game.home_score, game.away_score = 27, 24
    db.commit()
    assert "2026_01_BUF_KC" not in unplayed_game_ids(
        db, 2026, week, SPORT_NFL, now=before_kickoff
    )


def test_unplayed_game_ids_excludes_a_half_scored_row(db):
    """One score present means the game started; do not predict it."""
    from app.jobs.predict_week import unplayed_game_ids

    game = db.scalar(select(Game).where(Game.game_id == "2026_01_BUF_KC"))
    before_kickoff = game.kickoff_time - timedelta(hours=1)
    game.home_score, game.away_score = 27, None
    db.commit()
    assert "2026_01_BUF_KC" not in unplayed_game_ids(
        db, 2026, game.week, SPORT_NFL, now=before_kickoff
    )


def test_unplayed_game_ids_excludes_a_kicked_off_but_unscored_game(db):
    """A game that has kicked off but has no score yet (data lag, or a game
    still in progress) must not be re-predicted, even though both scores are
    still NULL -- re-predicting it would restamp predicted_at after kickoff
    while showing the exact same pre-game inputs."""
    from app.jobs.predict_week import unplayed_game_ids

    game = db.scalar(select(Game).where(Game.game_id == "2026_01_BUF_KC"))
    after_kickoff = game.kickoff_time + timedelta(hours=3)
    assert "2026_01_BUF_KC" not in unplayed_game_ids(
        db, 2026, game.week, SPORT_NFL, now=after_kickoff
    )


def test_unplayed_game_ids_still_includes_an_upcoming_game(db):
    """The same game, checked before its kickoff, is still a normal target."""
    from app.jobs.predict_week import unplayed_game_ids

    game = db.scalar(select(Game).where(Game.game_id == "2026_01_BUF_KC"))
    before_kickoff = game.kickoff_time - timedelta(hours=1)
    assert "2026_01_BUF_KC" in unplayed_game_ids(
        db, 2026, game.week, SPORT_NFL, now=before_kickoff
    )


def test_unplayed_game_ids_includes_null_kickoff_regardless_of_now(db):
    """A TBD (NULL) kickoff is a future game by definition and must stay
    eligible no matter how far forward `now` is."""
    from app.jobs.predict_week import unplayed_game_ids

    far_future = datetime(2030, 1, 1, tzinfo=UTC)
    assert "cfb_401800002" in unplayed_game_ids(
        db, 2026, 2, SPORT_CFB, now=far_future
    )


def test_default_week_skips_a_stale_week_with_a_permanently_unscored_game(db):
    """A cancelled week 1 game must not pin default_week to week 1 forever."""
    wk1 = db.scalar(select(Game).where(Game.game_id == "2026_01_BUF_KC"))
    wk1.home_score = None          # never resolved
    wk1.away_score = None
    wk1.kickoff_time = datetime(2026, 9, 10, 0, 20, tzinfo=UTC)
    db.commit()

    now = datetime(2026, 10, 1, tzinfo=UTC)   # weeks later
    assert default_week(db, 2026, SPORT_NFL, now=now) != 1
