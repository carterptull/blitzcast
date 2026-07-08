"""Load the current model artifact bundle referenced by latest.json."""

import json
from pathlib import Path

import joblib

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


def load_latest() -> dict:
    latest_path = ARTIFACTS_DIR / "latest.json"
    if not latest_path.exists():
        raise FileNotFoundError(
            "no model artifact found -- run `python -m ml.train` first"
        )
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    return joblib.load(ARTIFACTS_DIR / latest["artifact"])
