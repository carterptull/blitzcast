"""Batch-side hardening: calendar season default, step timeouts, final-only CFB
scores, CFB seed validation, and verified model artifacts."""

import argparse
import hashlib
import importlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import joblib
import pandas as pd
import pytest
from sqlalchemy import select

from app.models import SPORT_CFB, Game, Team
from app.season import current_season, resolve_season
from data_pipeline import refresh_week, refresh_week_cfb
from data_pipeline.cfb_games_loader import upsert_games
from data_pipeline.seed_cfb import clean_color, clean_logo, upsert_teams
from ml import model_store
from tests.test_cfb_pipeline import _venue_game, cfb_db  # noqa: F401

# --- season default ---


@pytest.mark.parametrize(
    "today,nfl,cfb",
    [
        (date(2026, 10, 15), 2026, 2026),
        (date(2027, 1, 20), 2026, 2026),
        (date(2027, 2, 28), 2026, 2026),
        (date(2027, 3, 1), 2027, 2026),
        (date(2027, 4, 1), 2027, 2026),
        (date(2027, 6, 1), 2027, 2027),
        (date(2027, 8, 1), 2027, 2027),
    ],
)
def test_current_season_follows_the_calendar(today, nfl, cfb):
    assert current_season("nfl", today) == nfl
    assert current_season("cfb", today) == cfb
    assert current_season("NFL", today) == nfl


def test_resolve_season_prefers_an_explicit_value():
    assert resolve_season(2019, "nfl") == 2019
    assert resolve_season(None, "cfb") == current_season("cfb")


def _captured_default(module_name, monkeypatch):
    """Run main() up to parse_args and return the parsed --season default."""
    mod = importlib.import_module(module_name)
    monkeypatch.setattr(mod, "current_season", lambda sport: {"nfl": 1111, "cfb": 2222}[sport])
    seen = {}

    def spy(self, *a, **kw):
        seen["season"] = self.get_default("season")
        raise SystemExit(0)

    monkeypatch.setattr(sys, "argv", ["x"])
    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", spy)
    with pytest.raises(SystemExit):
        mod.main()
    return seen["season"]


@pytest.mark.parametrize(
    "module",
    [
        "data_pipeline.refresh_week",
        "data_pipeline.refresh_schedule",
        "data_pipeline.refresh_stats",
        "data_pipeline.refresh_injuries",
    ],
)
def test_nfl_entrypoints_default_to_the_nfl_calendar_season(module, monkeypatch):
    assert _captured_default(module, monkeypatch) == 1111


@pytest.mark.parametrize(
    "module",
    [
        "data_pipeline.refresh_week_cfb",
        "data_pipeline.refresh_schedule_cfb",
        "data_pipeline.refresh_stats_cfb",
        "data_pipeline.refresh_polls_cfb",
    ],
)
def test_cfb_entrypoints_default_to_the_cfb_calendar_season(module, monkeypatch):
    assert _captured_default(module, monkeypatch) == 2222


@pytest.mark.parametrize(
    "module", ["app.jobs.predict_week", "app.jobs.coverage", "app.jobs.narration_eval"]
)
@pytest.mark.parametrize("sport", ["nfl", "cfb"])
def test_sport_aware_jobs_resolve_the_season_from_their_sport(module, sport, monkeypatch):
    mod = importlib.import_module(module)
    seen = []

    def spy(season, s):
        seen.append((season, s))
        raise SystemExit(0)

    monkeypatch.setattr(mod, "resolve_season", spy)
    week = ["--week", "1"] if module.endswith("narration_eval") else []
    monkeypatch.setattr(sys, "argv", ["x", "--sport", sport, *week])
    with pytest.raises(SystemExit):
        mod.main()
    assert seen == [(None, sport)]


# --- step timeouts ---


def test_run_step_passes_the_default_timeout(monkeypatch):
    seen = {}

    def fake(cmd, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(refresh_week.subprocess, "run", fake)
    assert refresh_week.run_step("x", ["mod"]) is True
    assert seen["timeout"] == 1800


def test_run_step_reports_a_timeout_and_returns_false(monkeypatch, capsys):
    def boom(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    monkeypatch.setattr(refresh_week.subprocess, "run", boom)
    assert refresh_week.run_step("odds refresh", ["mod"], timeout=5) is False
    assert "odds refresh timed out after 5s" in capsys.readouterr().out


@pytest.mark.parametrize(
    "module,argv,predict",
    [
        (refresh_week_cfb, ["refresh_week_cfb", "--season", "2026"], "cfb prediction batch"),
        (refresh_week, ["refresh_week", "--season", "2026"], "prediction batch"),
    ],
)
def test_the_prediction_batch_gets_the_long_timeout(module, argv, predict, monkeypatch):
    calls = {}

    def fake(name, args, timeout=1800):
        calls[name] = timeout
        return True

    monkeypatch.setattr(module, "run_step", fake)
    monkeypatch.setattr(sys, "argv", argv)
    module.main()
    assert calls[predict] == 5400
    assert all(t == 1800 for n, t in calls.items() if n != predict)


def test_engine_has_a_connect_timeout():
    code = "\n".join([
        "import sqlalchemy",
        "seen = {}",
        "real = sqlalchemy.create_engine",
        "def spy(*a, **kw):",
        "    seen.update(kw)",
        "    return real(*a, **kw)",
        "sqlalchemy.create_engine = spy",
        "import app.db",
        "print(seen['connect_args']['connect_timeout'])",
    ])
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True,
        cwd=Path(__file__).resolve().parent.parent,
    )
    assert out.stdout.strip() == "15"


# --- CFB scores only when final ---


def _scored(game_id, **over):
    df = _venue_game(game_id, "Aviva Stadium", True)
    for k, v in over.items():
        df[k] = v
    return df


def test_in_progress_cfb_game_stores_no_scores(cfb_db):  # noqa: F811
    upsert_games(cfb_db, _scored(401800001, homePoints=14, awayPoints=7, completed=False))
    game = cfb_db.get(Game, "cfb_401800001")
    assert game.home_score is None and game.away_score is None
    assert game.status == "scheduled"


def test_completed_cfb_game_stores_its_scores(cfb_db):  # noqa: F811
    upsert_games(cfb_db, _scored(401800002, homePoints=31, awayPoints=24, completed=True))
    game = cfb_db.get(Game, "cfb_401800002")
    assert (game.home_score, game.away_score) == (31, 24)
    assert game.status == "final"


def test_missing_completed_flag_with_both_points_keeps_the_scores(cfb_db):  # noqa: F811
    df = _scored(401800003, homePoints=3, awayPoints=0).drop(columns=["completed"])
    upsert_games(cfb_db, df)
    game = cfb_db.get(Game, "cfb_401800003")
    assert (game.home_score, game.away_score) == (3, 0)
    assert game.status == "final"


def test_a_scored_game_flagged_in_progress_loses_its_scores(cfb_db):  # noqa: F811
    upsert_games(cfb_db, _scored(401800004, homePoints=7, awayPoints=0, completed=True))
    upsert_games(cfb_db, _scored(401800004, homePoints=7, awayPoints=0, completed=False))
    game = cfb_db.get(Game, "cfb_401800004")
    assert game.home_score is None and game.away_score is None


# --- CFB seed validation ---

GOOD_LOGO = "https://a.espncdn.com/i/teamlogos/ncaa/500/61.png"


@pytest.mark.parametrize(
    "logo",
    [
        "http://a.espncdn.com/i/teamlogos/ncaa/500/61.png",
        "https://evil.example/i/teamlogos/ncaa/500/61.png",
        "https://a.espncdn.com/i/teamlogos/ncaa/500/61.svg",
        "javascript:alert(1)",
        "https://a.espncdn.com/i/teamlogos/ncaa/500/61.png?x=1",
        "https://a.espncdn.com/i/teamlogos/ncaa/500/61.png\nx",
        "",
        None,
    ],
)
def test_clean_logo_rejects_anything_but_the_espn_ncaa_png(logo):
    assert clean_logo(logo) is None


def test_clean_logo_keeps_the_espn_ncaa_png():
    assert clean_logo(GOOD_LOGO) == GOOD_LOGO


@pytest.mark.parametrize(
    "color,expected",
    [
        ("#BA0C2F", "#BA0C2F"), ("ba0c2f", "ba0c2f"), ("#123abc", "#123abc"),
        ("red", None), ("#12345", None), ("#12345g", None), ("#BA0C2F;x", None),
        ("url(x)", None), ("", None), (None, None),
    ],
)
def test_clean_color(color, expected):
    assert clean_color(color) == expected


def test_upsert_teams_nulls_bad_values_and_keeps_good_ones(cfb_db):  # noqa: F811
    teams = pd.DataFrame([
        {"school": "Georgia", "mascot": "Bulldogs", "conference": "SEC",
         "abbreviation": "UGA", "logos": [GOOD_LOGO], "color": "#BA0C2F",
         "alternateColor": "#000000"},
        {"school": "Alabama", "mascot": "Tide", "conference": "SEC",
         "abbreviation": "ALA", "logos": ["https://evil.example/x.png"],
         "color": "javascript:1", "alternateColor": "nope"},
    ])
    upsert_teams(cfb_db, teams, {"Georgia": "FBS", "Alabama": "FBS"}, {}, {})
    by_name = {t.name: t for t in cfb_db.scalars(select(Team).where(Team.sport == SPORT_CFB))}
    uga, ala = by_name["Georgia"], by_name["Alabama"]
    assert (uga.logo_url, uga.espn_id, uga.color, uga.alt_color) == (
        GOOD_LOGO, 61, "#BA0C2F", "#000000")
    assert (ala.logo_url, ala.color, ala.alt_color) == (None, None, None)


# --- artifact integrity ---


def _bundle(directory, name="model_9.joblib", sha=True, latest_name=None):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    joblib.dump({"model_version": "9"}, path)
    meta = {"model_version": "9", "artifact": latest_name or name}
    if sha:
        meta["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (directory / "latest.json").write_text(json.dumps(meta), encoding="utf-8")
    return path


def test_load_latest_verifies_a_matching_sha(tmp_path, monkeypatch):
    monkeypatch.setattr(model_store, "ARTIFACTS_DIR", tmp_path)
    _bundle(tmp_path)
    assert model_store.load_latest()["model_version"] == "9"


def test_load_latest_rejects_a_tampered_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(model_store, "ARTIFACTS_DIR", tmp_path)
    path = _bundle(tmp_path)
    path.write_bytes(path.read_bytes() + b"\x00")
    with pytest.raises(ValueError, match="sha256"):
        model_store.load_latest()


@pytest.mark.parametrize(
    "name", ["../x.joblib", "sub/x.joblib", "..\\x.joblib", "/abs/x.joblib"]
)
def test_load_latest_rejects_a_path_in_the_artifact_name(tmp_path, monkeypatch, name):
    monkeypatch.setattr(model_store, "ARTIFACTS_DIR", tmp_path)
    _bundle(tmp_path, latest_name=name)
    with pytest.raises(ValueError, match="artifact"):
        model_store.load_latest()


def test_load_latest_without_a_sha_still_loads(tmp_path, monkeypatch):
    monkeypatch.setattr(model_store, "ARTIFACTS_DIR", tmp_path)
    _bundle(tmp_path, sha=False)
    assert model_store.load_latest()["model_version"] == "9"


@pytest.mark.parametrize("sport", ["NFL", "CFB"])
def test_committed_artifacts_carry_a_sha_and_verify(sport):
    art_dir = model_store.artifacts_dir(sport)
    latest = json.loads((art_dir / "latest.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256((art_dir / latest["artifact"]).read_bytes()).hexdigest()
    assert latest["sha256"] == digest
    assert model_store.load_latest(sport)["model_version"] == latest["model_version"]


def test_write_latest_records_the_artifact_sha(tmp_path):
    path = tmp_path / "model_1.joblib"
    joblib.dump({"a": 1}, path)
    model_store.write_latest(tmp_path, "1", path)
    meta = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert meta == {
        "model_version": "1",
        "artifact": "model_1.joblib",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
