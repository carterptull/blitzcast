"""predict_week selection predicates and fact-sheet shaping."""

import logging
import re
from collections import Counter
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.jobs import predict_week
from app.jobs.predict_week import (
    Narration,
    default_week,
    existing_narrative,
    narrate_safely,
    narration_summary,
    still_true,
)
from app.models import SPORT_CFB, SPORT_NFL, Game, Team
from app.services.narrate import check_narration
from tests.test_fallback_narration import CAL, UNLV, _game, _team

BILLS = dict(name="Bills", full_name="Buffalo Bills", abbr="BUF")
CHIEFS = dict(name="Chiefs", full_name="Kansas City Chiefs", abbr="KC")


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


SECRET = "postgresql://user:hunter2@db.example/prod"
MINIMAL = "Our model gives KC 60% and BUF 40%."


def _narrate_args(db, **row_cols):
    row = _row(
        "2026_01_BUF_KC", has_market_line=1.0, has_market_spread=1.0,
        home_abbr="KC", away_abbr="BUF", **row_cols,
    )
    return db, row, 0.6, [], {}, {}


def _raise(exc):
    def boom(*args, **kwargs):
        raise exc
    return boom


def test_narrate_safely_survives_a_fact_sheet_failure(db, monkeypatch, caplog):
    monkeypatch.setattr(predict_week, "facts_for_row", _raise(ValueError(SECRET)))
    with caplog.at_level(logging.WARNING, logger="app.jobs.predict_week"):
        assert narrate_safely(*_narrate_args(db)) == Narration(MINIMAL, "minimal")
    assert "fact sheet failed for 2026_01_BUF_KC: ValueError" in caplog.text
    assert SECRET not in caplog.text


def test_narrate_safely_survives_a_narrator_failure(db, monkeypatch, caplog):
    monkeypatch.setattr(predict_week, "narrate", _raise(RuntimeError(SECRET)))
    with caplog.at_level(logging.WARNING, logger="app.jobs.predict_week"):
        result = narrate_safely(*_narrate_args(db))
    assert result.source == "fallback" and result.text
    assert "narration draft failed for 2026_01_BUF_KC: RuntimeError" in caplog.text
    assert SECRET not in caplog.text


def test_narrate_safely_logs_no_draft_failure_without_an_exception(db, monkeypatch, caplog):
    monkeypatch.setattr(predict_week, "narrate", lambda facts: None)
    with caplog.at_level(logging.INFO, logger="app.jobs.predict_week"):
        assert narrate_safely(*_narrate_args(db)).source == "fallback"
    assert "failed" not in caplog.text and "skipped" not in caplog.text


def test_narrate_safely_rolls_back_after_a_database_error(db, monkeypatch):
    rollbacks = []
    monkeypatch.setattr(db, "rollback", lambda: rollbacks.append(1))
    monkeypatch.setattr(predict_week, "facts_for_row", _raise(SQLAlchemyError(SECRET)))
    assert narrate_safely(*_narrate_args(db)) == Narration(MINIMAL, "minimal")
    assert rollbacks == [1]


def test_minimal_line_when_the_fact_sheet_fails_is_still_stored(db, monkeypatch):
    from app.jobs.predict_week import narrate_and_store

    db, row, prob, factors, ranks, prev_ranks = _narrate_args(db)
    monkeypatch.setattr(predict_week, "facts_for_row", _raise(ValueError(SECRET)))
    # A stored narration cannot be verified without today's fact sheet.
    predict_week.upsert_prediction(db, "2026_01_BUF_KC", "1.0.0", 0.55, [], "older text")
    db.commit()
    result = narrate_and_store(db, row, "1.0.0", prob, factors, ranks, prev_ranks)
    assert result == Narration(MINIMAL, "minimal")
    stored = predict_week._stored_prediction(db, "2026_01_BUF_KC", "1.0.0")
    assert stored.llm_narrative == MINIMAL
    assert stored.home_win_prob == 0.6


@pytest.mark.parametrize("prob", [0.0, 0.004, 0.3, 0.495, 0.5, 0.505, 0.51, 0.7, 0.996, 1.0])
def test_minimal_line_holds_only_abbreviations_and_percentages(prob):
    from app.services.fallback_narration import minimal_narration

    text = minimal_narration("KC", "BUF", prob)
    home, away = round(prob * 100), round((1 - prob) * 100)
    if home == 50:
        assert text == "Our model sees a coin flip between KC and BUF."
    else:
        assert text == f"Our model gives KC {home}% and BUF {away}%."
    words = re.sub(r"\b(?:KC|BUF|\d{1,3}%)", "", text)
    assert set(words.split()) <= {"Our", "model", "gives", "and", ".", "sees", "a", "coin",
                                  "flip", "between"}


def test_minimal_line_when_the_fallback_raises(db, monkeypatch, caplog):
    monkeypatch.setattr(predict_week, "narrate", lambda facts: None)
    monkeypatch.setattr(predict_week, "fallback_narration", _raise(IndexError(SECRET)))
    with caplog.at_level(logging.WARNING, logger="app.jobs.predict_week"):
        assert narrate_safely(*_narrate_args(db)) == Narration(MINIMAL, "minimal")
    assert "IndexError" in caplog.text and SECRET not in caplog.text


def test_none_only_when_even_the_minimal_line_fails(db, monkeypatch, caplog):
    monkeypatch.setattr(predict_week, "facts_for_row", _raise(ValueError(SECRET)))
    monkeypatch.setattr(predict_week, "minimal_narration", _raise(KeyError(SECRET)))
    with caplog.at_level(logging.WARNING, logger="app.jobs.predict_week"):
        assert narrate_safely(*_narrate_args(db)) == Narration(None, "none")
    assert "minimal narration failed for 2026_01_BUF_KC: KeyError" in caplog.text
    assert SECRET not in caplog.text


def test_narrate_safely_returns_the_narration(db, monkeypatch):
    from ml.features import build_features

    features = build_features(db, seasons=[2026], sport=SPORT_NFL)
    row = features[features["game_id"] == "2026_01_BUF_KC"].iloc[0]
    seen = []

    def fake_narrate(facts):
        seen.append(facts)
        return "ok"

    monkeypatch.setattr(predict_week, "narrate", fake_narrate)
    assert narrate_safely(db, row, 0.6, [], {}, {}) == Narration("ok", "llm")
    assert seen[0].home.name == "Chiefs"


GOOD_PREVIOUS = "Our model gives the Chiefs 60% and the Bills 40%."
STALE_PREVIOUS = "The Chiefs are favored by 3 points, and our model gives them 60%."
# Passes check_narration's +-1 tolerance, but the model now says 60%.
OFF_BY_ONE_PREVIOUS = "Our model gives the Chiefs 61% and the Bills 39%."


@pytest.mark.parametrize(
    ("draft", "previous", "expected"),
    [
        (None, GOOD_PREVIOUS, Narration(GOOD_PREVIOUS, "kept")),
        (None, STALE_PREVIOUS, "fallback"),
        (None, OFF_BY_ONE_PREVIOUS, "fallback"),
        (None, None, "fallback"),
        ("", None, "fallback"),
        ("fresh", GOOD_PREVIOUS, Narration("fresh", "llm")),
    ],
    ids=[
        "keeps-valid-previous", "drops-stale-previous", "drops-off-by-one-previous",
        "no-previous", "empty-draft", "new-draft-wins",
    ],
)
def test_narrate_safely_chain(db, monkeypatch, draft, previous, expected):
    monkeypatch.setattr(predict_week, "narrate", lambda facts: draft)
    result = narrate_safely(*_narrate_args(db), previous=previous)
    if expected == "fallback":
        assert result.source == "fallback"
        assert result.text and result.text != previous
        assert "Chiefs" in result.text and "60%" in result.text
    else:
        assert result == expected


def test_narrate_safely_keeps_a_valid_previous_when_the_narrator_raises(db, monkeypatch):
    monkeypatch.setattr(predict_week, "narrate", _raise(RuntimeError("down")))
    assert narrate_safely(*_narrate_args(db), previous=GOOD_PREVIOUS) == Narration(
        GOOD_PREVIOUS, "kept"
    )


def test_narrate_safely_falls_back_when_the_previous_check_raises(db, monkeypatch, caplog):
    monkeypatch.setattr(predict_week, "narrate", lambda facts: None)
    real_check = predict_week.check_narration
    calls = []

    def check(text, facts):
        calls.append(text)
        if text == GOOD_PREVIOUS:
            raise KeyError(SECRET)
        return real_check(text, facts)

    monkeypatch.setattr(predict_week, "check_narration", check)
    with caplog.at_level(logging.WARNING, logger="app.jobs.predict_week"):
        result = narrate_safely(*_narrate_args(db), previous=GOOD_PREVIOUS)
    assert result.source == "fallback"
    assert "KeyError" in caplog.text and SECRET not in caplog.text


def test_minimal_line_when_the_fallback_fails_its_check(db, monkeypatch, caplog):
    monkeypatch.setattr(predict_week, "narrate", lambda facts: None)
    monkeypatch.setattr(predict_week, "fallback_narration", lambda facts: "Chiefs by 77%.")
    with caplog.at_level(logging.WARNING, logger="app.jobs.predict_week"):
        assert narrate_safely(*_narrate_args(db)) == Narration(MINIMAL, "minimal")
    assert "fallback narration rejected" in caplog.text


def test_minimal_line_when_the_fallback_has_a_colon(db, monkeypatch):
    monkeypatch.setattr(predict_week, "narrate", lambda facts: None)
    monkeypatch.setattr(
        predict_week, "fallback_narration", lambda facts: "Our model: the Chiefs at 60%."
    )
    assert narrate_safely(*_narrate_args(db)) == Narration(MINIMAL, "minimal")


def test_narration_summary_counts_each_source():
    sources = Counter({"llm": 3, "kept": 2, "fallback": 1, "minimal": 1})
    assert narration_summary(sources) == [
        "narration: 3 written, 2 kept, 1 fallback, 1 minimal, 0 none"
    ]
    sources["none"] = 1
    lines = narration_summary(sources)
    assert lines[0] == "narration: 3 written, 2 kept, 1 fallback, 1 minimal, 1 none"
    assert lines[1] == "WARNING: 1 game has no booth narration"
    sources["none"] = 2
    assert narration_summary(sources)[1] == "WARNING: 2 games have no booth narration"


def _bills_chiefs(p: float, weather: str | None):
    return _game(
        "NFL", _team(**BILLS, record="3-1"), _team(**CHIEFS, record="2-2"), p, 3.0,
        venue="Highmark Stadium in Orchard Park", weather=weather,
    )


SNOWY_PREVIOUS = (
    "It is 31 degrees in Orchard Park with snow likely and wind at 22 mph, and the Bills are "
    "3-1. Our model gives the Bills 60%, and they are favored by 3 points."
)


@pytest.mark.parametrize("weather", ["48 degrees, wind 5 mph", None])
def test_still_true_drops_yesterdays_weather_and_percentage(weather):
    facts = _bills_chiefs(0.61, weather)
    assert check_narration(SNOWY_PREVIOUS, facts) is None  # the guardrail alone keeps it
    assert not still_true(SNOWY_PREVIOUS, facts)


def test_still_true_drops_a_lean_that_flipped():
    facts = _game("CFB", _team(**UNLV, record="3-1"), _team(**CAL, record="2-2"), 0.497, None)
    text = "Our model gives UNLV 51% and California 49%."
    assert check_narration(text, facts) is None
    assert not still_true(text, facts)


def test_still_true_drops_a_coin_flip_that_is_no_longer_one():
    text = "Our model sees a coin flip, with 50% for each side."
    facts = _game("CFB", _team(**UNLV), _team(**CAL), 0.514, None)
    assert check_narration(text, facts) is None
    assert not still_true(text, facts)
    assert still_true(text, _game("CFB", _team(**UNLV), _team(**CAL), 0.5, None))


def test_still_true_drops_a_weather_claim_with_no_weather_today():
    text = "Snow is likely in Orchard Park, and our model gives the Bills 61%."
    assert still_true(text, _bills_chiefs(0.61, "34 degrees, wind 8 mph, rain or snow likely"))
    assert not still_true(text, _bills_chiefs(0.61, None))
    assert not still_true(text, _bills_chiefs(0.61, "48 degrees, wind 5 mph"))


def test_still_true_keeps_a_text_that_is_exactly_true_today():
    text = (
        "It is 48 degrees in Orchard Park with wind at 5 mph, and the Bills are 3-1. Our model "
        "gives the Bills 61% and the Chiefs 39%, and the Bills are favored by 3 points."
    )
    facts = _bills_chiefs(0.61, "48 degrees, wind 5 mph")
    assert still_true(text, facts)
    assert not still_true(text.replace("61%", "60%"), facts)
    assert not still_true(text.replace(", and the Bills are 3-1", "; the Bills are 3-1"), facts)
    assert not still_true(text, _bills_chiefs(0.62, "48 degrees, wind 5 mph"))
    assert not still_true(text, _bills_chiefs(0.61, "47 degrees, wind 5 mph"))


def test_existing_narrative_reads_the_stored_text(db):
    from app.jobs.predict_week import upsert_prediction

    assert existing_narrative(db, "2026_01_BUF_KC", "1.0.0") is None
    upsert_prediction(db, "2026_01_BUF_KC", "1.0.0", 0.6, [], "stored text")
    db.commit()
    assert existing_narrative(db, "2026_01_BUF_KC", "1.0.0") == "stored text"
    assert existing_narrative(db, "2026_01_BUF_KC", "9.9.9") is None
    assert existing_narrative(db, "no_such_game", "1.0.0") is None


def test_still_true_never_keeps_a_link():
    facts = _bills_chiefs(0.6, None)
    good = "Our model gives the Bills 60% and the Chiefs 40%."
    assert still_true(good, facts)
    assert not still_true(f"Free picks at scam.example. {good}", facts)


def test_fallback_rejection_log_carries_only_a_category(db, monkeypatch, caplog):
    monkeypatch.setattr(predict_week, "narrate", lambda facts: None)
    monkeypatch.setattr(
        predict_week, "fallback_reason",
        lambda text, facts: "names not in the fact sheet: evil\nFORGED LOG LINE",
    )
    with caplog.at_level(logging.WARNING, logger="app.jobs.predict_week"):
        assert narrate_safely(*_narrate_args(db)) == Narration(MINIMAL, "minimal")
    assert "FORGED" not in caplog.text and "evil" not in caplog.text
    assert all("\n" not in r.getMessage() for r in caplog.records)
    assert "fallback narration rejected for 2026_01_BUF_KC: names not in the fact sheet" in (
        caplog.text
    )


class _FakeModel:
    def predict_proba(self, x):
        import numpy as np

        return np.array([[0.4, 0.6]])


class _Identity:
    def transform(self, raw):
        return raw


def _run_main(db, monkeypatch, narrate_fn, capsys, **patches):
    from contextlib import contextmanager

    @contextmanager
    def scope():
        yield db

    real_unplayed = predict_week.unplayed_game_ids
    monkeypatch.setattr(predict_week, "load_latest", lambda sport: {
        "model": _FakeModel(), "calibrator": _Identity(), "feature_columns": ["elo_diff"],
    })
    monkeypatch.setattr(predict_week, "make_explainer", lambda model: None)
    monkeypatch.setattr(predict_week, "top_factors", lambda *a, **kw: [])
    monkeypatch.setattr(predict_week, "session_scope", scope)
    monkeypatch.setattr(
        predict_week, "unplayed_game_ids",
        lambda *a: real_unplayed(*a, now=datetime(2026, 9, 1, tzinfo=UTC)),
    )
    monkeypatch.setattr(predict_week, "narrate", narrate_fn)
    for name, value in patches.items():
        monkeypatch.setattr(predict_week, name, value)
    commits = []
    real_commit = db.commit
    monkeypatch.setattr(db, "commit", lambda: (commits.append(1), real_commit()))
    monkeypatch.setattr("sys.argv", ["predict_week", "--season", "2026", "--week", "1"])
    predict_week.main()
    return capsys.readouterr().out, commits


def _stored_texts(db):
    from app.models import Prediction

    rows = db.scalars(select(Prediction).where(Prediction.model_version == "1.0.0")).all()
    return {p.game_id: p.llm_narrative for p in rows if p.game_id.startswith("2026_01")}


def test_main_counts_each_tier_and_commits_every_game(db, monkeypatch, capsys):
    def draft(facts):
        return "A fresh booth draft." if facts.home.abbr == "KC" else None

    out, commits = _run_main(db, monkeypatch, draft, capsys)
    assert "narration: 1 written, 0 kept, 1 fallback, 0 minimal, 0 none" in out
    assert "WARNING" not in out
    assert len(commits) == 2
    stored = _stored_texts(db)
    assert stored["2026_01_BUF_KC"] == "A fresh booth draft."
    assert stored["2026_01_PHI_DAL"] and "60%" in stored["2026_01_PHI_DAL"]


def test_main_warns_only_when_a_game_has_no_narration(db, monkeypatch, capsys):
    real_facts = predict_week.facts_for_row

    def facts(db_, row, *a):
        if row["game_id"] == "2026_01_PHI_DAL":
            raise ValueError("no sheet")
        return real_facts(db_, row, *a)

    out, commits = _run_main(
        db, monkeypatch, lambda f: "A fresh booth draft.", capsys,
        facts_for_row=facts, minimal_narration=_raise(KeyError("no abbr")),
    )
    assert "narration: 1 written, 0 kept, 0 fallback, 0 minimal, 1 none" in out
    assert "WARNING: 1 game has no booth narration" in out
    assert len(commits) == 2
    assert _stored_texts(db) == {
        "2026_01_BUF_KC": "A fresh booth draft.", "2026_01_PHI_DAL": None,
    }
