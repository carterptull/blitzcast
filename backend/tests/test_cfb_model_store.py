"""load_latest(sport) resolves the flat NFL path and the cfb/ subfolder."""

import json

import joblib
import pytest

from app.models import SPORT_CFB
from ml import model_store


def _write_bundle(directory, version):
    directory.mkdir(parents=True, exist_ok=True)
    name = f"model_{version}.joblib"
    joblib.dump({"model_version": version}, directory / name)
    (directory / "latest.json").write_text(
        json.dumps({"model_version": version, "artifact": name}), encoding="utf-8"
    )


def test_load_latest_resolves_per_sport_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(model_store, "ARTIFACTS_DIR", tmp_path)
    _write_bundle(tmp_path, "0.1.0")  # NFL stays flat (legacy layout)
    _write_bundle(tmp_path / "cfb", "cfb-0.1.0")

    assert model_store.load_latest()["model_version"] == "0.1.0"
    assert model_store.load_latest(SPORT_CFB)["model_version"] == "cfb-0.1.0"
    assert model_store.load_latest(sport="cfb")["model_version"] == "cfb-0.1.0"


def test_load_latest_missing_artifact_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(model_store, "ARTIFACTS_DIR", tmp_path)
    _write_bundle(tmp_path, "0.1.0")
    with pytest.raises(FileNotFoundError):
        model_store.load_latest(SPORT_CFB)


def test_artifacts_dir_layout(tmp_path, monkeypatch):
    monkeypatch.setattr(model_store, "ARTIFACTS_DIR", tmp_path)
    assert model_store.artifacts_dir() == tmp_path
    assert model_store.artifacts_dir("NFL") == tmp_path
    assert model_store.artifacts_dir(SPORT_CFB) == tmp_path / "cfb"
