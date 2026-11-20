"""Guardrail and template behavior for postseason occasions and CFP seeds."""

from dataclasses import replace

from app.services.fallback_narration import fallback_narration, fallback_reason
from app.services.narrate import check_narration
from tests.test_narrate import FACTS, OSU, TEX, _facts, _team

# Ohio State (No. 4 seed) vs Texas (No. 5 seed) in the Rose Bowl; model Texas 55%.
TEX_SEED = replace(TEX, seed=5)
OSU_SEED = replace(OSU, seed=4)
ROSE = _facts(
    OSU_SEED, TEX_SEED, 0.45, -1.5, total=49.5, is_neutral_site=True,
    venue="Rose Bowl in Pasadena",
    matchup_note="Rose Bowl, College Football Playoff quarterfinal, neutral site",
    occasion="Rose Bowl, College Football Playoff quarterfinal, neutral site",
    stakes="Win and advance; lose and the season ends",
)
BASE = "Our model leans Texas at 55% in the Rose Bowl, with Texas favored by 1.5."


def test_rose_bowl_base_text_passes():
    """PS-B6: occasion words on the sheet pass the name rule."""
    assert check_narration(BASE, ROSE) is None


def test_seed_claim_matching_the_sheet_passes():
    """PS-B6: a seed that matches the sheet passes in every written form."""
    for claim in ("Texas is the No. 5 seed.", "Texas is the 5 seed.", "The 5-seed Longhorns roll."):
        assert check_narration(f"{BASE} {claim}", ROSE) is None, claim


def test_wrong_seed_fails():
    """PS-B6: a seed that is not on the sheet is rejected."""
    reason = check_narration(f"{BASE} Texas is the No. 7 seed.", ROSE)
    assert reason and "seed" in reason


def test_nfl_seed_claim_fails():
    """PS-B6: NFL sheets carry no seeds, so any seed claim is rejected."""
    from tests.test_narrate import RAMS_AT_LAC

    text = "Our model gives the Chargers 58%, the No. 1 seed at home."
    reason = check_narration(text, RAMS_AT_LAC)
    assert reason and "seed" in reason


def test_rank_claims_still_checked_as_ranks():
    """PS-B6: a No. 7 rank claim (not a seed) still goes through the rank rule."""
    ranked = replace(ROSE, home=replace(OSU_SEED, rank=7))
    assert check_narration(f"{BASE} No. 7 Ohio State is at home.", ranked) is None
    reason = check_narration(f"{BASE} No. 9 Ohio State is at home.", ranked)
    assert reason and "rank" in reason


def test_occasion_words_need_the_sheet():
    """PS-B6: Super Bowl, Rose Bowl, Quarterfinal, CFP and LXI fail when not on the sheet."""
    for words in ("the Super Bowl", "the Rose Bowl", "this Quarterfinal", "the CFP",
                  "Super Bowl LXI"):
        text = (
            "A top-five heavyweight fight in Austin on Saturday night. Our model leans Ohio "
            f"State at 55% on the road in {words}, even with Texas favored by 1.5."
        )
        assert check_narration(text, FACTS) is not None, words


def test_fallback_opener_names_the_occasion():
    """PS-B7: postseason templates open with the occasion."""
    text = fallback_narration(ROSE)
    assert text.startswith("In the Rose Bowl, ")
    assert fallback_reason(text, ROSE) is None
    sb_home = _team("Eagles", "Philadelphia Eagles", "PHI", "Eagles")
    sb_away = _team("Chiefs", "Kansas City Chiefs", "KC", "Chiefs")
    sb = _facts(sb_home, sb_away, 0.53, 1.5, sport="NFL", is_neutral_site=True,
                venue="SoFi Stadium in Inglewood",
                matchup_note="Super Bowl LXI, neutral site",
                occasion="Super Bowl LXI, neutral site",
                stakes="Winner wins the Super Bowl")
    sb_text = fallback_narration(sb)
    assert sb_text.startswith("In Super Bowl LXI, ")
    assert fallback_reason(sb_text, sb) is None


def test_regular_season_opener_unchanged():
    """PS-B7: regular-season templates keep their opener."""
    text = fallback_narration(FACTS)
    assert not text.startswith("In the ") and not text.startswith("In Super Bowl")


def test_seed_attributed_to_the_wrong_team_fails():
    """PS-B6: a real seed said of the other team is rejected (Texas is 5, Ohio State is 4)."""
    reason = check_narration(f"{BASE} Ohio State, the No. 5 seed, hosts nothing here.", ROSE)
    assert reason is not None


def test_seed_variants_are_checked_and_never_slip_past_both_rules():
    """PS-B6: seeding/seeds are seed-checked; seed-like words still hit the rank rule."""
    for text in ("Texas earned the No. 9 seeding.", "The No. 9 seeds meet here.",
                 "Texas holds the 9-seed."):
        reason = check_narration(f"{BASE} {text}", ROSE)
        assert reason and "seed" in reason, text
    reason = check_narration(f"{BASE} The #9 seedling crowd roars.", ROSE)
    assert reason and "rank" in reason
