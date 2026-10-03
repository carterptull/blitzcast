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


@pytest.mark.parametrize("lead", [
    "Picks at scam dot com.", "Call 555-0199.", "Text 8005 550 199.", "Hxxp scam.",
    "Visit scam․com.",
])
def test_still_true_never_keeps_a_link_or_phone_evasion(lead):
    facts = _bills_chiefs(0.6, None)
    assert not still_true(f"{lead} Our model gives the Bills 60% and the Chiefs 40%.", facts)


@pytest.mark.parametrize("abbr", [
    "SCAM.IO", "8005550199", "1234567", "800-5550", "kc", "", " ", "A B", "TOOLONGAB", None,
])
def test_minimal_line_rejects_a_hostile_abbreviation(abbr):
    from app.services.fallback_narration import minimal_narration

    with pytest.raises(ValueError):
        minimal_narration(abbr, "BUF", 0.61)
    with pytest.raises(ValueError):
        minimal_narration("KC", abbr, 0.5)


@pytest.mark.parametrize("abbr", ["KC", "BUF", "UNLV", "A&M", "OSU", "MIAOH", "M-OH"])
def test_minimal_line_accepts_real_abbreviations(abbr):
    from app.services.fallback_narration import minimal_narration

    assert minimal_narration(abbr, "BUF", 0.61) == f"Our model gives {abbr} 61% and BUF 39%."


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


class _FailOnceModel:
    """Raises on the first call only, so one game fails and the next succeeds."""

    def __init__(self, exc):
        self.exc = exc
        self.calls = 0

    def predict_proba(self, x):
        self.calls += 1
        if self.calls == 1:
            raise self.exc
        return _FakeModel().predict_proba(x)


def _run_main(
    db, monkeypatch, narrate_fn, capsys, model=None, argv=None, clock=None, commits=None,
    **patches,
):
    """Run main against the test session. `clock` stands in for the wall clock:
    any selection made without an explicit `now` reads it too, so a clock that
    advances mid-run exposes a second, later reading."""
    from contextlib import contextmanager

    @contextmanager
    def scope():
        yield db

    from app.jobs import coverage

    clock = clock or (lambda: datetime(2026, 9, 1, tzinfo=UTC))
    real_select = predict_week.select_target_ids

    def select(db_, season, sport, **kw):
        return real_select(db_, season, sport, **{**kw, "now": kw.get("now") or clock()})

    monkeypatch.setattr(coverage, "select_target_ids", select)
    monkeypatch.setattr(predict_week, "select_target_ids", select)
    monkeypatch.setattr(predict_week, "_utc_now", clock)
    monkeypatch.setattr(predict_week, "load_latest", lambda sport: {
        "model": model or _FakeModel(), "calibrator": _Identity(),
        "feature_columns": ["elo_diff"],
    })
    monkeypatch.setattr(predict_week, "make_explainer", lambda model: None)
    monkeypatch.setattr(predict_week, "top_factors", lambda *a, **kw: [])
    monkeypatch.setattr(predict_week, "session_scope", scope)
    monkeypatch.setattr(predict_week, "narrate", narrate_fn)
    for name, value in patches.items():
        monkeypatch.setattr(predict_week, name, value)
    commits = [] if commits is None else commits
    real_commit = db.commit
    monkeypatch.setattr(db, "commit", lambda: (commits.append(1), real_commit()))
    monkeypatch.setattr(
        "sys.argv", argv or ["predict_week", "--season", "2026", "--week", "1"]
    )
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
    assert "predictions: 2 ok, 0 failed" in out
    assert "narration: 1 written, 0 kept, 1 fallback, 0 minimal, 0 none" in out
    assert "coverage: 2 upcoming games, 0 missing a prediction, 0 missing a booth section" in out
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

    commits: list = []
    with pytest.raises(SystemExit) as exit_info:
        _run_main(
            db, monkeypatch, lambda f: "A fresh booth draft.", capsys, commits=commits,
            facts_for_row=facts, minimal_narration=_raise(KeyError("no abbr")),
        )
    assert exit_info.value.code == 1
    assert len(commits) == 2
    out = capsys.readouterr().out
    assert "narration: 1 written, 0 kept, 0 fallback, 0 minimal, 1 none" in out
    assert "WARNING: 1 game has no booth narration" in out
    assert "coverage: 2 upcoming games, 0 missing a prediction, 1 missing a booth section" in out
    assert "WARNING: no booth section for 2026_01_PHI_DAL" in out
    assert _stored_texts(db) == {
        "2026_01_BUF_KC": "A fresh booth draft.", "2026_01_PHI_DAL": None,
    }


NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


def _add_game(db, game_id, week, kickoff, game_date=None, home_score=None, away_score=None):
    teams = {t.abbr: t.team_id for t in db.query(Team).filter_by(sport=SPORT_NFL)}
    db.add(
        Game(
            game_id=game_id, sport=SPORT_NFL, season=2026, week=week,
            game_date=game_date or kickoff.date(), kickoff_time=kickoff,
            home_team_id=teams["KC"], away_team_id=teams["PHI"],
            home_score=home_score, away_score=away_score, status="scheduled",
        )
    )


def _lookahead_slate(db):
    """Week 1 is the default week at NOW; week 2 straddles the 7 day horizon."""
    _add_game(db, "w1_kicked_off", 1, datetime(2026, 9, 12, 0, 0, tzinfo=UTC))
    _add_game(db, "w1_tbd_late", 1, None, game_date=date(2026, 9, 25))
    _add_game(db, "w2_thursday", 2, datetime(2026, 9, 18, 0, 20, tzinfo=UTC))
    _add_game(db, "w2_tbd_in_window", 2, None, game_date=date(2026, 9, 18))
    _add_game(db, "w2_sunday", 2, datetime(2026, 9, 20, 17, 0, tzinfo=UTC))
    _add_game(db, "w2_tbd_beyond", 2, None, game_date=date(2026, 9, 21))
    _add_game(db, "w2_half_scored", 2, datetime(2026, 9, 17, 0, 20, tzinfo=UTC),
              home_score=7)
    _add_game(db, "w2_scored", 2, datetime(2026, 9, 17, 0, 20, tzinfo=UTC),
              home_score=21, away_score=14)
    db.commit()


def test_select_target_ids_adds_games_inside_the_lookahead_window(db):
    from app.jobs.predict_week import select_target_ids

    _lookahead_slate(db)
    assert default_week(db, 2026, SPORT_NFL, now=NOW) == 1
    assert select_target_ids(db, 2026, SPORT_NFL, now=NOW) == {
        "2026_01_BUF_KC", "2026_01_PHI_DAL", "w1_tbd_late", "w2_thursday", "w2_tbd_in_window",
    }


def test_select_target_ids_window_length_is_a_parameter(db):
    from app.jobs.predict_week import LOOKAHEAD_DAYS, select_target_ids

    _lookahead_slate(db)
    assert LOOKAHEAD_DAYS == 7
    ids = select_target_ids(db, 2026, SPORT_NFL, now=NOW, lookahead_days=9)
    assert {"w2_sunday", "w2_tbd_beyond"} <= ids
    assert not {"w1_kicked_off", "w2_half_scored", "w2_scored"} & ids


def test_select_target_ids_with_an_explicit_week_keeps_the_old_selection(db):
    from app.jobs.predict_week import select_target_ids, unplayed_game_ids

    _lookahead_slate(db)
    for week in (1, 2):
        assert select_target_ids(db, 2026, SPORT_NFL, now=NOW, week=week) == unplayed_game_ids(
            db, 2026, week, SPORT_NFL, now=NOW
        )
    assert select_target_ids(db, 2026, SPORT_NFL, now=NOW, week=1) == {
        "2026_01_BUF_KC", "2026_01_PHI_DAL", "w1_tbd_late",
    }


def test_select_target_ids_is_sport_and_season_scoped(db):
    from app.jobs.predict_week import select_target_ids

    _lookahead_slate(db)
    assert select_target_ids(db, 2026, SPORT_CFB, now=NOW) == {"cfb_401800002"}
    assert select_target_ids(db, 2025, SPORT_NFL, now=NOW) == set()


def _predictor(model):
    return predict_week.Predictor(
        model=model, calibrator=_Identity(), explainer=None,
        feature_columns=["elo_diff"], sport=SPORT_NFL, version="1.0.0",
    )


def _week1_rows(db):
    from ml.features import build_features

    features = build_features(db, seasons=[2026], sport=SPORT_NFL)
    week = features[features["week"] == 1].set_index("game_id", drop=False)
    return week.loc["2026_01_BUF_KC"], week.loc["2026_01_PHI_DAL"]


def _isolation_setup(db, monkeypatch):
    monkeypatch.setattr(predict_week, "top_factors", lambda *a, **kw: [])
    monkeypatch.setattr(predict_week, "narrate", lambda facts: "A fresh booth draft.")
    commits, rollbacks = [], []
    real_commit, real_rollback = db.commit, db.rollback
    monkeypatch.setattr(db, "commit", lambda: (commits.append(1), real_commit()))
    monkeypatch.setattr(db, "rollback", lambda: (rollbacks.append(1), real_rollback()))
    return commits, rollbacks


def test_predict_one_isolates_a_model_failure(db, monkeypatch, caplog):
    from app.jobs.predict_week import predict_one

    commits, rollbacks = _isolation_setup(db, monkeypatch)
    first, second = _week1_rows(db)
    predictor = _predictor(_FailOnceModel(ValueError(SECRET)))
    with caplog.at_level(logging.WARNING, logger="app.jobs.predict_week"):
        results = [predict_one(db, row, predictor, {}, {}) for row in (first, second)]
    assert results[0] is None
    assert results[1] == Narration("A fresh booth draft.", "llm")
    assert "prediction failed for 2026_01_BUF_KC: ValueError" in caplog.text
    assert SECRET not in caplog.text
    assert rollbacks == [1] and commits == [1]
    assert _stored_texts(db)["2026_01_PHI_DAL"] == "A fresh booth draft."
    assert predict_week._stored_prediction(db, "2026_01_BUF_KC", "1.0.0").home_win_prob == 0.61


def test_predict_one_rolls_back_a_storage_failure(db, monkeypatch, caplog):
    from app.jobs.predict_week import predict_one

    commits, rollbacks = _isolation_setup(db, monkeypatch)
    first, second = _week1_rows(db)
    real_upsert = predict_week.upsert_prediction
    calls = []

    def upsert(*a, **kw):
        calls.append(1)
        real_upsert(*a, **kw)
        if len(calls) == 1:
            raise SQLAlchemyError(SECRET)

    monkeypatch.setattr(predict_week, "upsert_prediction", upsert)
    predictor = _predictor(_FakeModel())
    with caplog.at_level(logging.WARNING, logger="app.jobs.predict_week"):
        assert predict_one(db, second, predictor, {}, {}) is None
        assert predict_one(db, first, predictor, {}, {}) is not None
    assert "prediction failed for 2026_01_PHI_DAL: SQLAlchemyError" in caplog.text
    assert SECRET not in caplog.text
    assert rollbacks == [1] and commits == [1]
    assert predict_week._stored_prediction(db, "2026_01_PHI_DAL", "1.0.0") is None
    assert _stored_texts(db)["2026_01_BUF_KC"] == "A fresh booth draft."


def test_main_finishes_the_slate_and_exits_nonzero_on_a_failed_game(db, monkeypatch, capsys):
    from app.models import Prediction

    db.query(Prediction).filter_by(game_id="2026_01_BUF_KC").delete()
    db.commit()
    with pytest.raises(SystemExit) as exit_info:
        _run_main(
            db, monkeypatch, lambda f: "A fresh booth draft.", capsys,
            model=_FailOnceModel(RuntimeError(SECRET)),
        )
    assert exit_info.value.code == 1
    out = capsys.readouterr().out
    assert "predictions: 1 ok, 1 failed" in out
    assert re.search(r"WARNING: prediction failed for 1 game: 2026_01_\w+", out)
    assert "coverage: 2 upcoming games, 1 missing a prediction, 0 missing a booth section" in out
    assert re.search(r"WARNING: no prediction for 2026_01_\w+", out)
    assert "narration: 1 written, 0 kept, 0 fallback, 0 minimal, 0 none" in out
    assert SECRET not in out
    assert sum(text == "A fresh booth draft." for text in _stored_texts(db).values()) == 1


def test_main_without_a_week_predicts_the_lookahead_window(db, monkeypatch, capsys):
    _add_game(db, "w2_early", 2, datetime(2026, 9, 5, 0, 20, tzinfo=UTC))
    db.commit()
    out, commits = _run_main(
        db, monkeypatch, lambda f: "A fresh booth draft.", capsys,
        argv=["predict_week", "--season", "2026"],
    )
    assert "predicting 3 NFL games for 2026 weeks 1-2" in out
    assert "predictions: 3 ok, 0 failed" in out
    assert len(commits) == 3


def test_ranks_for_week_reads_each_game_week_once(db, monkeypatch):
    from app.jobs.predict_week import ranks_for_week
    from app.models import PollRank

    ala = db.query(Team).filter_by(sport=SPORT_CFB, abbr="ALA").one()
    db.add(PollRank(sport=SPORT_CFB, season=2026, week=2, poll="AP Top 25",
                    team_id=ala.team_id, rank=5))
    db.commit()
    real = predict_week.poll_ranks_entering
    reads = []

    def counting(db_, sport, season, week):
        reads.append(week)
        return real(db_, sport, season, week)

    monkeypatch.setattr(predict_week, "poll_ranks_entering", counting)
    cache: dict = {}
    week1 = ranks_for_week(db, SPORT_CFB, 2026, 1, cache)
    week2 = ranks_for_week(db, SPORT_CFB, 2026, 2, cache)
    week3 = ranks_for_week(db, SPORT_CFB, 2026, 3, cache)
    assert week1[0][ala.team_id] == 7 and week1[1] == {}
    assert week2 == ({ala.team_id: 5}, week1[0])
    assert week3 == ({}, {ala.team_id: 5})
    assert ranks_for_week(db, SPORT_CFB, 2026, 2, cache) == week2
    assert sorted(reads) == [1, 2, 3]


def test_exit_status_is_one_when_any_game_failed_or_coverage_has_gaps():
    from app.jobs.coverage import Coverage, Gap, coverage_outcome

    assert coverage_outcome(Coverage(3, []))[1] == 0
    assert coverage_outcome(Coverage(3, [Gap("g", "narration")]))[1] == 1
    assert coverage_outcome(Coverage(3, [Gap("g", "prediction")]))[1] == 1


def _advancing_clock(start, later):
    """The wall clock for a long run: `start` on the first reading, `later` after."""
    readings = []

    def clock():
        readings.append(1)
        return start if len(readings) == 1 else later

    return clock


def test_main_reads_the_clock_once_so_a_long_run_audits_its_own_window(
    db, monkeypatch, capsys
):
    # Kicks off just past the start-of-run horizon: never selected, so the end
    # of the run must not count it as a gap even though the clock has moved on.
    _add_game(db, "w2_past_edge", 2, NOW + timedelta(days=7, minutes=1))
    db.commit()
    out, commits = _run_main(
        db, monkeypatch, lambda f: "A fresh booth draft.", capsys,
        argv=["predict_week", "--season", "2026"],
        clock=_advancing_clock(NOW, NOW + timedelta(hours=2)),
    )
    assert "predicting 2 NFL games for 2026 week 1" in out
    assert "coverage: 2 upcoming games, 0 missing a prediction, 0 missing a booth section" in out
    assert "WARNING" not in out
    assert "prediction batch complete" in out
    assert len(commits) == 2


def test_a_game_that_kicks_off_during_the_run_still_counts_as_covered(db, monkeypatch, capsys):
    _add_game(db, "w1_mid_run", 1, NOW + timedelta(hours=1))
    db.commit()
    out, _ = _run_main(
        db, monkeypatch, lambda f: "A fresh booth draft.", capsys,
        argv=["predict_week", "--season", "2026"],
        clock=_advancing_clock(NOW, NOW + timedelta(hours=2)),
    )
    assert "predictions: 3 ok, 0 failed" in out
    assert "coverage: 3 upcoming games, 0 missing a prediction, 0 missing a booth section" in out
    assert "prediction batch complete" in out


def test_main_audits_only_the_current_model_version(db, monkeypatch, capsys):
    from app.models import Prediction

    db.query(Prediction).filter(Prediction.game_id.like("2026_01_%")).delete()
    for game_id in ("2026_01_BUF_KC", "2026_01_PHI_DAL"):
        db.add(Prediction(
            game_id=game_id, model_version="0.9.0", home_win_prob=0.5,
            predicted_at=datetime(2026, 8, 30, tzinfo=UTC), shap_top_features=[],
            llm_narrative="An older model's booth section.",
        ))
    db.commit()
    with pytest.raises(SystemExit) as exit_info:
        _run_main(
            db, monkeypatch, lambda f: "A fresh booth draft.", capsys,
            model=_FailOnceModel(RuntimeError("boom")),
        )
    assert exit_info.value.code == 1
    out = capsys.readouterr().out
    assert "coverage: 2 upcoming games, 1 missing a prediction, 0 missing a booth section" in out


def test_main_reports_coverage_when_no_selected_game_has_a_feature_row(
    db, monkeypatch, capsys
):
    from ml.features import build_features

    def no_week1_rows(db_, seasons, sport):
        features = build_features(db_, seasons=seasons, sport=sport)
        return features[~features["game_id"].str.startswith("2026_01")]

    commits: list = []
    with pytest.raises(SystemExit) as exit_info:
        _run_main(
            db, monkeypatch, lambda f: "A fresh booth draft.", capsys, commits=commits,
            build_features=no_week1_rows,
        )
    assert exit_info.value.code == 1
    out = capsys.readouterr().out
    assert "WARNING: no feature rows for 2 selected NFL games" in out
    assert "coverage: 2 upcoming games, 1 missing a prediction, 1 missing a booth section" in out
    assert "prediction batch complete" not in out
    assert commits == []


def test_main_with_nothing_to_predict_exits_quietly(db, monkeypatch, capsys):
    out, commits = _run_main(
        db, monkeypatch, lambda f: "A fresh booth draft.", capsys,
        argv=["predict_week", "--season", "2026"],
        clock=lambda: datetime(2027, 3, 1, tzinfo=UTC),
    )
    assert out.strip() == "no unplayed NFL games found for season 2026"
    assert commits == []


def test_main_explicit_week_all_final_prints_the_skipped_line(db, monkeypatch, capsys):
    db.query(Game).filter(Game.game_id.like("2026_01_%")).update(
        {"home_score": 24, "away_score": 17}, synchronize_session=False
    )
    db.commit()
    out, commits = _run_main(db, monkeypatch, lambda f: "A fresh booth draft.", capsys)
    assert out.splitlines() == [
        "skipping 2 already-final NFL games",
        "no unplayed NFL games found for 2026 week 1",
    ]
    assert commits == []


def test_select_target_ids_horizon_is_inclusive_to_the_second(db):
    from app.jobs.predict_week import select_target_ids

    _add_game(db, "at_horizon", 3, NOW + timedelta(days=7))
    _add_game(db, "past_horizon", 3, NOW + timedelta(days=7, seconds=1))
    _add_game(db, "tbd_horizon_day", 3, None, game_date=(NOW + timedelta(days=7)).date())
    db.commit()
    ids = select_target_ids(db, 2026, SPORT_NFL, now=NOW)
    assert {"at_horizon", "tbd_horizon_day"} <= ids
    assert "past_horizon" not in ids


def test_select_target_ids_with_no_default_week_uses_only_the_window(db, monkeypatch):
    from app.jobs.predict_week import select_target_ids

    _add_game(db, "in_window", 3, NOW + timedelta(days=3))
    _add_game(db, "beyond", 4, NOW + timedelta(days=10))
    db.commit()
    window = {"2026_01_BUF_KC", "2026_01_PHI_DAL", "in_window"}
    monkeypatch.setattr(predict_week, "default_week", lambda *a, **kw: 4)
    assert select_target_ids(db, 2026, SPORT_NFL, now=NOW) == window | {"beyond"}
    monkeypatch.setattr(predict_week, "default_week", lambda *a, **kw: None)
    assert select_target_ids(db, 2026, SPORT_NFL, now=NOW) == window
