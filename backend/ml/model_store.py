"""Load the current model artifact bundle referenced by latest.json.

NFL artifacts stay flat in ml/artifacts/ (backward compatible with the
trained artifact); other sports live in ml/artifacts/<sport>/.
"""

import hashlib
import json
from pathlib import Path

import joblib

from app.models import SPORT_NFL

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


def artifacts_dir(sport: str = SPORT_NFL) -> Path:
    if sport.upper() == SPORT_NFL:
        return ARTIFACTS_DIR
    return ARTIFACTS_DIR / sport.lower()


def load_latest(sport: str = SPORT_NFL) -> dict:
    art_dir = artifacts_dir(sport)
    latest_path = art_dir / "latest.json"
    if not latest_path.exists():
        raise FileNotFoundError(
            f"no {sport} model artifact found -- run `python -m ml.train` first"
        )
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    name = latest["artifact"]
    if Path(name).name != name or "\\" in name:
        raise ValueError(f"latest.json artifact must be a bare file name, got {name!r}")
    path = art_dir / name
    expected = latest.get("sha256")
    if expected is not None and _sha256(path) != expected:
        raise ValueError(f"{name} does not match the sha256 recorded in latest.json")
    return joblib.load(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_latest(art_dir: Path, version: str, artifact_path: Path) -> None:
    meta = {
        "model_version": version,
        "artifact": artifact_path.name,
        "sha256": _sha256(artifact_path),
    }
    (art_dir / "latest.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
