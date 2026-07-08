"""LLM narration of model output. The LLM never computes or alters the
probability -- it only explains numbers it is handed. A failed narration
must never block a prediction (returns None)."""

import logging
import re
import time

import anthropic

from app.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are narrating a football win-probability prediction produced by a "
    "statistical model, in the voice of an energetic radio play-by-play "
    "broadcaster — fun, vivid, and packed with the specific stats you're "
    "given. You are given the probability and the top contributing factors. "
    "Never state a different probability than the one provided. Never invent "
    "stats not given. Keep it to 2-4 sentences, exciting but grounded in the "
    "real numbers, no betting advice."
)

_PCT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)", re.IGNORECASE)


def _build_user_content(payload: dict) -> str:
    lines = [
        f"Home team: {payload['home_name']} ({payload['home_abbr']})",
        f"Away team: {payload['away_name']} ({payload['away_abbr']})",
        f"Home win probability: {payload['home_win_prob']:.0%}",
        f"Away win probability: {1 - payload['home_win_prob']:.0%}",
        "Top factors (positive = favors home team):",
    ]
    for f in payload.get("factors", []):
        lines.append(f"- {f['label']}: {f['value']:+.3f} (favors {f['direction']})")
    for key, label in (
        ("spread_home", "Vegas spread (home)"),
        ("rest_note", "Rest"),
        ("qb_note", "QB status"),
        ("weather_note", "Weather"),
    ):
        if payload.get(key) is not None:
            lines.append(f"{label}: {payload[key]}")
    lines.append(
        "Write 2-4 sentences of play-by-play-style narration leading with the "
        "favored team and explaining why, using only the numbers above."
    )
    return "\n".join(lines)


def _percentages_consistent(text: str, home_win_prob: float) -> bool:
    """Any percentage mentioned must match the home or away win probability."""
    valid = {round(home_win_prob * 100), round((1 - home_win_prob) * 100)}
    for match in _PCT_RE.finditer(text):
        pct = float(match.group(1))
        if not any(abs(pct - v) <= 1.0 for v in valid):
            return False
    return True


def _call_api(client: anthropic.Anthropic, model: str, user_content: str) -> str:
    response = client.messages.create(
        model=model,
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return text.strip().strip("*_#`").strip()


def narrate(payload: dict) -> str | None:
    """Generate a narrative for a prediction. Returns None on any failure.

    payload: home_name, home_abbr, away_name, away_abbr, home_win_prob,
    factors ([{label, value, direction}, ...]), plus optional color keys
    (spread_home, rest_note, qb_note, weather_note).
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        logger.info("ANTHROPIC_API_KEY not set; skipping narration")
        return None

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    user_content = _build_user_content(payload)

    for attempt in range(2):
        try:
            text = _call_api(client, settings.anthropic_model, user_content)
            if text and _percentages_consistent(text, payload["home_win_prob"]):
                return text
            logger.warning("narration failed percentage sanity check; retrying")
        except Exception as exc:
            logger.warning("narration attempt %d failed: %s", attempt + 1, exc)
        if attempt == 0:
            time.sleep(2)
    return None
