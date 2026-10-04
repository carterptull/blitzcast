"""End-of-run coverage check: upcoming games with no live prediction or no booth
section. Read-only, and shares its window with predict_week."""

from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from app.jobs import coverage
from app.jobs.coverage import Coverage, Gap, coverage_gaps, coverage_outcome
from app.models import SPORT_CFB, SPORT_NFL, Prediction
from tests.test_predict_week import NOW, _add_game

LIVE = "1.0.0"


def _predict(db, game_id, narrative, version=LIVE, at=datetime(2026, 9, 10, tzinfo=UTC)):
    db.add(
        Prediction(
            game_id=game_id, model_version=version, home_win_prob=0.6,
            predicted_at=at, shap_top_features=[], llm_narrative=narrative,
        )
    )
    db.commit()


def _by_game(gaps):
    return {g.game_id: g.missing for g in gaps}


def test_a_game_with_no_live_prediction_is_a_prediction_gap(db):
    gaps = coverage_gaps(db, 2026, SPORT_NFL, now=NOW)
    assert Gap("2026_01_PHI_DAL", "prediction") in gaps


def test_blank_or_null_narration_is_a_narration_gap(db):
    # The seed already stores a NULL narrative for 2026_01_BUF_KC.
    _add_game(db, "blank", 1, datetime(2026, 9, 14, 17, tzinfo=UTC))
    _add_game(db, "spaces", 1, datetime(2026, 9, 14, 17, tzinfo=UTC))
    db.commit()
    _predict(db, "blank", "")
    _predict(db, "spaces", "  \n ")
    got = _by_game(coverage_gaps(db, 2026, SPORT_NFL, now=NOW))
    assert got["2026_01_BUF_KC"] == "narration"
    assert got["blank"] == "narration"
    assert got["spaces"] == "narration"


def test_a_fully_covered_game_is_not_listed(db):
    _add_game(db, "covered", 1, datetime(2026, 9, 14, 17, tzinfo=UTC))
    db.commit()
    _predict(db, "covered", "A booth section.")
    assert "covered" not in _by_game(coverage_gaps(db, 2026, SPORT_NFL, now=NOW))


def test_backtest_rows_do_not_count_as_predictions(db):
    _add_game(db, "bt_only", 1, datetime(2026, 9, 14, 17, tzinfo=UTC))
    _add_game(db, "bt_and_live", 1, datetime(2026, 9, 14, 17, tzinfo=UTC))
    db.commit()
    _predict(db, "bt_only", "Backtest text.", version="backtest-1.0.0")
    _predict(db, "bt_and_live", "Backtest text.", version="backtest-1.0.0")
    _predict(db, "bt_and_live", None)
    got = _by_game(coverage_gaps(db, 2026, SPORT_NFL, now=NOW))
    assert got["bt_only"] == "prediction"
    assert got["bt_and_live"] == "narration"


def test_the_latest_live_prediction_decides_narration(db):
    _add_game(db, "newer_blank", 1, datetime(2026, 9, 14, 17, tzinfo=UTC))
    _add_game(db, "newer_text", 1, datetime(2026, 9, 14, 17, tzinfo=UTC))
    db.commit()
    old, new = datetime(2026, 9, 9, tzinfo=UTC), datetime(2026, 9, 11, tzinfo=UTC)
    _predict(db, "newer_blank", "Old text.", version="0.9.0", at=old)
    _predict(db, "newer_blank", None, version="1.0.0", at=new)
    _predict(db, "newer_text", None, version="0.9.0", at=old)
    _predict(db, "newer_text", "New text.", version="1.0.0", at=new)
    got = _by_game(coverage_gaps(db, 2026, SPORT_NFL, now=NOW))
    assert got["newer_blank"] == "narration"
    assert "newer_text" not in got


def test_version_restricts_which_live_rows_count(db):
    _add_game(db, "old_version", 1, datetime(2026, 9, 14, 17, tzinfo=UTC))
    db.commit()
    _predict(db, "old_version", "Text.", version="0.9.0")
    assert "old_version" not in _by_game(coverage_gaps(db, 2026, SPORT_NFL, now=NOW))
    got = _by_game(coverage_gaps(db, 2026, SPORT_NFL, version="1.0.0", now=NOW))
    assert got["old_version"] == "prediction"


def test_games_outside_the_window_or_already_decided_are_ignored(db):
    _add_game(db, "kicked_off", 1, datetime(2026, 9, 12, 0, 0, tzinfo=UTC))
    _add_game(db, "beyond", 3, datetime(2026, 9, 27, 17, tzinfo=UTC))
    _add_game(db, "final", 2, datetime(2026, 9, 17, 0, 20, tzinfo=UTC),
              home_score=21, away_score=14)
    _add_game(db, "half", 2, datetime(2026, 9, 17, 0, 20, tzinfo=UTC), home_score=7)
    db.commit()
    got = _by_game(coverage_gaps(db, 2026, SPORT_NFL, now=NOW))
    assert not {"kicked_off", "beyond", "final", "half"} & set(got)


def test_a_tbd_kickoff_in_the_default_week_is_included(db):
    _add_game(db, "tbd", 1, None, game_date=datetime(2026, 9, 25).date())
    db.commit()
    assert _by_game(coverage_gaps(db, 2026, SPORT_NFL, now=NOW))["tbd"] == "prediction"


def test_a_long_past_tbd_game_is_not_a_gap(db, monkeypatch):
    from tests.test_predict_week import LATE_NOW, _stale_tbd_slate

    _stale_tbd_slate(db, monkeypatch)
    got = _by_game(coverage_gaps(db, 2026, SPORT_NFL, now=LATE_NOW))
    assert got == {"tbd_today": "prediction", "tbd_tomorrow": "prediction"}


def test_gaps_are_sport_scoped_and_sorted(db):
    nfl = coverage_gaps(db, 2026, SPORT_NFL, now=NOW)
    assert [g.game_id for g in nfl] == sorted(g.game_id for g in nfl)
    assert not any(g.game_id.startswith("cfb_") for g in nfl)
    assert _by_game(coverage_gaps(db, 2026, SPORT_CFB, now=NOW))["cfb_401800002"] == "prediction"


def test_an_explicit_week_limits_the_check_to_that_week(db):
    _add_game(db, "w2", 2, datetime(2026, 9, 18, 0, 20, tzinfo=UTC))
    db.commit()
    got = _by_game(coverage_gaps(db, 2026, SPORT_NFL, now=NOW, week=2))
    assert got == {"w2": "prediction"}


def test_the_check_never_writes(db):
    before = db.query(Prediction).count()
    coverage_gaps(db, 2026, SPORT_NFL, now=NOW)
    assert not (db.new or db.dirty or db.deleted)
    assert db.query(Prediction).count() == before


def test_outcome_is_quiet_and_zero_when_covered():
    lines, status = coverage_outcome(Coverage(upcoming=2, gaps=[]))
    assert lines == [
        "coverage: 2 upcoming games, 0 missing a prediction, 0 missing a booth section"
    ]
    assert status == 0


def test_outcome_warns_per_category_and_fails():
    gaps = [Gap("a", "prediction"), Gap("b", "narration"), Gap("c", "narration")]
    lines, status = coverage_outcome(Coverage(upcoming=5, gaps=gaps))
    assert lines == [
        "coverage: 5 upcoming games, 1 missing a prediction, 2 missing a booth section",
        "WARNING: no prediction for a",
        "WARNING: no booth section for b, c",
    ]
    assert status == 1


def _patch_session(monkeypatch, db):
    @contextmanager
    def scope():
        yield db

    real = coverage.select_target_ids
    monkeypatch.setattr(coverage, "session_scope", scope)
    monkeypatch.setattr(coverage, "get_settings", lambda: _Settings())
    monkeypatch.setattr(
        coverage, "select_target_ids",
        lambda db_, season, sport, **kw: real(db_, season, sport, **{**kw, "now": NOW}),
    )


def test_cli_exits_one_and_prints_gaps(db, monkeypatch, capsys):
    _patch_session(monkeypatch, db)
    monkeypatch.setattr("sys.argv", ["coverage", "--season", "2026"])
    with pytest.raises(SystemExit) as exit_info:
        coverage.main()
    assert exit_info.value.code == 1
    out = capsys.readouterr().out
    assert "coverage: 2 upcoming games, 1 missing a prediction, 1 missing a booth section" in out
    assert "WARNING: no prediction for 2026_01_PHI_DAL" in out
    assert "WARNING: no booth section for 2026_01_BUF_KC" in out


def test_cli_returns_cleanly_when_covered(db, monkeypatch, capsys):
    _patch_session(monkeypatch, db)
    _predict(db, "2026_01_PHI_DAL", "A booth section.")
    db.query(Prediction).filter_by(game_id="2026_01_BUF_KC").update({"llm_narrative": "Text."})
    db.commit()
    monkeypatch.setattr("sys.argv", ["coverage", "--season", "2026", "--sport", "nfl"])
    coverage.main()
    assert "0 missing a prediction, 0 missing a booth section" in capsys.readouterr().out


class _Settings:
    def model_version_for(self, sport):
        return {"NFL": "1.0.0", "CFB": "cfb-1.0.0"}[sport]


def _old_version_only(db):
    db.query(Prediction).filter(Prediction.game_id.like("2026_01_%")).delete()
    db.commit()
    for game_id in ("2026_01_BUF_KC", "2026_01_PHI_DAL"):
        _predict(db, game_id, "An older model's booth section.", version="0.9.0")


def test_cli_audits_the_current_model_version(db, monkeypatch, capsys):
    _patch_session(monkeypatch, db)
    _old_version_only(db)
    monkeypatch.setattr("sys.argv", ["coverage", "--season", "2026"])
    with pytest.raises(SystemExit) as exit_info:
        coverage.main()
    assert exit_info.value.code == 1
    out = capsys.readouterr().out
    assert "coverage: 2 upcoming games, 2 missing a prediction, 0 missing a booth section" in out
    assert "model version" not in out


def test_cli_without_a_model_version_counts_any_live_row_and_says_so(db, monkeypatch, capsys):
    def unavailable():
        raise RuntimeError("no settings")

    _patch_session(monkeypatch, db)
    _old_version_only(db)
    monkeypatch.setattr(coverage, "get_settings", unavailable)
    monkeypatch.setattr("sys.argv", ["coverage", "--season", "2026"])
    coverage.main()
    out = capsys.readouterr().out.splitlines()
    assert out == [
        "coverage: no current model version for NFL, counting any live prediction",
        "coverage: 2 upcoming games, 0 missing a prediction, 0 missing a booth section",
    ]


def test_coverage_report_audits_the_given_clock_and_version(db, capsys):
    from app.jobs.predict_week import coverage_report

    _add_game(db, "old_version", 1, datetime(2026, 9, 14, 17, tzinfo=UTC))
    db.commit()
    _predict(db, "old_version", "Text.", version="0.9.0")
    assert coverage_report(db, 2026, SPORT_NFL, None, now=NOW) == 1
    assert "WARNING: no prediction for 2026_01_PHI_DAL\n" in capsys.readouterr().out
    assert coverage_report(db, 2026, SPORT_NFL, None, now=NOW, version=LIVE) == 1
    assert "WARNING: no prediction for 2026_01_PHI_DAL, old_version" in capsys.readouterr().out
