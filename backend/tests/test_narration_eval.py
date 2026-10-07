from contextlib import contextmanager
from datetime import UTC, datetime

import pandas as pd
import pytest

from app.jobs import narration_eval
from app.jobs.narration_eval import reason_category, summarize
from app.jobs.predict_week import facts_for_row
from app.models import Prediction, Team
from app.services.fallback_narration import fallback_narration
from app.services.narrate import NarrationResult, check_narration
from ml.features import build_features


def test_summarize_counts_passes_and_reasons():
    results = [
        ("g1", NarrationResult(text="ok text here", attempts=1)),
        ("g2", NarrationResult(text=None, attempts=3, rejections=["too long (95 words)"] * 3)),
        ("g3", NarrationResult(text="fine", attempts=2, rejections=["uses banned phrase 'folks'"])),
    ]
    s = summarize(results)
    assert s["games"] == 3 and s["passed"] == 2
    assert s["mean_attempts"] == 2.0
    assert s["reasons"]["too long"] == 3
    assert s["reasons"]["uses banned phrase"] == 1
    assert s["mean_words"] == pytest.approx(2.0)


def test_summarize_empty():
    s = summarize([])
    assert s["games"] == 0 and s["passed"] == 0 and s["reasons"] == {}


@pytest.mark.parametrize(
    ("reason", "category"),
    [
        ("too long (95 words, limit 69)", "too long"),
        ("cites a percentage (99%) the model did not produce", "cites a percentage"),
        ("names not in the fact sheet: Zed Quarterback", "names not in the fact sheet"),
        ("api error: AuthenticationError", "api error"),
        (
            "cites 62% for Buffalo but that rank belongs to Kansas City",
            "cites another team's number",
        ),
        ("something with sk-ant-secret in it", "other"),
        ("too long", "too long"),
    ],
)
def test_reason_category_is_a_fixed_label(reason, category):
    assert reason_category(reason) == category


@pytest.mark.parametrize(
    ("reason", "category"),
    [
        ("says the wrong team is the betting favorite (...)", "market favorite wrong"),
        ("calls the betting favorite the underdog (the market favors X)", "market favorite wrong"),
        ("calls the wrong team the model's favorite (the model favors X)", "model favorite wrong"),
        ("cites 5 points but the line is 3", "cites points off the line"),
        ("cites 21-17 but the fact sheet has no such score", "cites a fact the sheet lacks"),
        ("gives X 60% but the model has X at 55%", "wrong percentage for a team"),
        ("puts Z on the wrong team (the Bills list Z)", "player on the wrong team"),
        ("mentions a betting market but no line exists", "mentions a betting market"),
        ("cites a total but none is posted", "cites a total"),
    ],
)
def test_reason_category_covers_the_guardrail_reasons(reason, category):
    assert reason_category(reason) == category


def test_reason_category_never_echoes_untrusted_text():
    nasty = "api error: https://example.test/?key=sk-ant-123"
    assert "sk-ant" not in reason_category(nasty)
    assert reason_category(nasty) == "api error"


@pytest.fixture()
def eval_db(db, monkeypatch):
    @contextmanager
    def fake_session():
        try:
            yield db
        finally:
            db.rollback()

    monkeypatch.setattr(narration_eval, "_read_session", fake_session)
    db.add(
        Prediction(
            game_id="2026_01_PHI_DAL",
            model_version="1.0.0",
            home_win_prob=0.55,
            predicted_at=datetime(2026, 9, 10, 12, 0, tzinfo=UTC),
            shap_top_features=[],
            llm_narrative=None,
        )
    )
    db.commit()
    return db


def _facts(db, game_id, prob):
    features = build_features(db, seasons=[2026], sport="NFL")
    row = features[features["game_id"] == game_id].iloc[0]
    return facts_for_row(db, row, prob, [], {}, {})


def test_stored_scores_each_narration_against_todays_guardrail(eval_db, capsys):
    good = fallback_narration(_facts(eval_db, "2026_01_PHI_DAL", 0.55))
    assert check_narration(good, _facts(eval_db, "2026_01_PHI_DAL", 0.55)) is None
    for game_id, text in (
        ("2026_01_BUF_KC", "Kansas City wins 99% of the time."),
        ("2026_01_PHI_DAL", good),
    ):
        eval_db.query(Prediction).filter_by(game_id=game_id).one().llm_narrative = text
    eval_db.commit()

    code = narration_eval.main(["--sport", "nfl", "--week", "1", "--stored"])
    out = capsys.readouterr().out

    assert code == 0
    assert "2026_01_BUF_KC stored=fail (cites a percentage)" in out
    assert "2026_01_PHI_DAL stored=pass" in out
    assert "fallback=pass" in out and "fallback=FAIL" not in out
    assert "games=2" in out and "passed=1" in out
    assert "fallback_passed=2/2" in out
    assert "Kansas City wins 99%" not in out


def test_stored_reports_missing_narration_without_failing_the_run(eval_db, capsys):
    code = narration_eval.main(["--sport", "nfl", "--week", "1", "--stored"])
    out = capsys.readouterr().out
    assert code == 0
    assert "stored=none" in out


def test_stored_is_read_only(eval_db, capsys):
    before = eval_db.query(Prediction).count()
    narration_eval.main(["--sport", "nfl", "--week", "1", "--stored"])
    eval_db.expire_all()
    assert eval_db.query(Prediction).count() == before
    assert all(p.llm_narrative is None for p in eval_db.query(Prediction).all())
    assert not eval_db.dirty and not eval_db.new


def test_fallback_always_passes_for_seeded_games(eval_db, capsys):
    assert narration_eval.main(["--sport", "nfl", "--week", "1", "--stored"]) == 0
    out = capsys.readouterr().out
    assert out.count("fallback=pass") == 2
    assert "FAIL" not in out


@pytest.mark.parametrize("spread", [None, 0.0, 2.5])
def test_fallback_passes_for_a_seeded_cfb_game(eval_db, spread):
    row = pd.Series({"game_id": "cfb_401800001", "market_spread_home": spread or 0.0,
                     "has_market_spread": 0.0 if spread is None else 1.0})
    ranks = {t.team_id: i for i, t in enumerate(eval_db.query(Team).filter_by(sport="CFB"), 3)}
    facts = facts_for_row(eval_db, row, 0.55, [], ranks, {})
    assert narration_eval._fallback_ok(facts)


def test_fallback_failure_is_loud_and_fails_the_run(eval_db, capsys, monkeypatch):
    monkeypatch.setattr(narration_eval, "fallback_narration", lambda facts: "Folks, big game.")
    code = narration_eval.main(["--sport", "nfl", "--week", "1", "--stored"])
    captured = capsys.readouterr()
    assert code == 1
    assert "BUG: fallback narration failed the guardrail" in captured.out + captured.err
    assert "fallback=FAIL" in captured.out


def test_fresh_mode_requires_spend_tokens_flag(eval_db, capsys, monkeypatch):
    def boom(facts):
        raise AssertionError("generate must not run without --spend-tokens")

    monkeypatch.setattr(narration_eval, "generate", boom)
    code = narration_eval.main(["--sport", "nfl", "--week", "1"])
    captured = capsys.readouterr()
    assert code == 2
    assert "spends Anthropic tokens" in captured.out + captured.err
    assert "2026_01_BUF_KC" not in captured.out


def test_fresh_mode_with_flag_uses_generate_and_hides_raw_errors(eval_db, capsys, monkeypatch):
    calls = []

    def fake_generate(facts):
        calls.append(facts.home.abbr)
        return NarrationResult(
            text=None, attempts=1, rejections=["api error: https://x.test/?key=sk-ant-1"]
        )

    monkeypatch.setattr(narration_eval, "generate", fake_generate)
    code = narration_eval.main(["--sport", "nfl", "--week", "1", "--spend-tokens"])
    out = capsys.readouterr().out
    assert code == 0
    assert sorted(calls) == ["DAL", "KC"]
    assert "spends Anthropic tokens" in out
    assert "sk-ant" not in out and "https://" not in out
    assert "api error" in out


def test_fresh_mode_skips_near_even_games_like_production(eval_db, capsys, monkeypatch):
    eval_db.query(Prediction).filter_by(game_id="2026_01_PHI_DAL").one().home_win_prob = 0.503
    eval_db.commit()
    calls = []

    def fake_generate(facts):
        calls.append(facts.home.abbr)
        return NarrationResult(text=None, attempts=1, rejections=["empty response"])

    monkeypatch.setattr(narration_eval, "generate", fake_generate)
    code = narration_eval.main(["--sport", "nfl", "--week", "1", "--spend-tokens"])
    out = capsys.readouterr().out
    assert code == 0
    assert calls == ["KC"]
    assert "2026_01_PHI_DAL near-even: template only fallback=pass" in out
    assert "fallback_passed=2/2" in out


def test_fallback_ok_uses_the_production_fallback_check(eval_db, monkeypatch):
    facts = _facts(eval_db, "2026_01_PHI_DAL", 0.55)
    text = fallback_narration(facts).replace("Our model", "Our model:", 1)
    assert "Our model:" in text and check_narration(text, facts) is None
    monkeypatch.setattr(narration_eval, "fallback_narration", lambda f: text)
    assert not narration_eval._fallback_ok(facts)


def test_evaluate_rolls_back_after_a_database_error(eval_db, capsys, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    rollbacks = []
    real_rollback = eval_db.rollback
    monkeypatch.setattr(eval_db, "rollback", lambda: (rollbacks.append(1), real_rollback()))

    def boom(*args, **kwargs):
        raise SQLAlchemyError("aborted")

    monkeypatch.setattr(narration_eval, "facts_for_row", boom)
    results, _ = narration_eval.evaluate(eval_db, "NFL", 2026, 1, 20, stored=True)
    assert [r.rejections for _, r in results] == [["fact sheet failed"]] * 2
    assert len(rollbacks) == 2
