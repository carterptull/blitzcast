"""Load the current model artifact bundle referenced by latest.json.

NFL artifacts stay flat in ml/artifacts/ (backward compatible with the
trained artifact); other sports live in ml/artifacts/<sport>/.
"""

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
    return joblib.load(art_dir / latest["artifact"])
