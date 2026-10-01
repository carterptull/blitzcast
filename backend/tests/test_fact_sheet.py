from app.models import Game
from app.services.fact_sheet import build_game_facts, market_favorite, render_fact_sheet


def _factor(feature, direction):
    return {"feature": feature, "label": feature, "value": 0.05, "direction": direction}


FACTORS = [
    _factor("market_spread_home", "home"),
    _factor("week_number", "home"),
    _factor("epa_off_diff", "away"),
    _factor("elo_diff", "home"),
]


def _facts(db, game_id, spread):
    game = db.get(Game, game_id)
    return build_game_facts(db, game, 0.61, FACTORS, spread_home=spread)


def test_week1_game_facts(db):
    f = _facts(db, "2026_01_BUF_KC", 2.5)
    assert f.home.name == "Chiefs" and f.home.mascot == "Chiefs"
    assert f.home.record == "0-0" and f.home.last_game is None
    assert f.when == "Sunday afternoon"
    assert f.venue == "Test Field in Testville"
    assert f.matchup_note == "AFC matchup"
    assert f.last_meeting == "Chiefs won 24-17 in Week 6 of 2025"
    assert f.away.injuries == ("Test Quarterback (QB) is listed Out",)
    assert f.home.injuries == ()


def test_market_is_written_in_words_with_the_right_favorite(db):
    f = _facts(db, "2026_01_BUF_KC", 2.5)
    fav, dog = market_favorite(f)
    assert (fav.abbr, dog.abbr) == ("KC", "BUF")
    sheet = render_fact_sheet(f)
    assert "Betting market: Chiefs favored by 2.5 points (KC -2.5, BUF +2.5)" in sheet


def test_no_line_says_so(db):
    f = _facts(db, "2026_01_BUF_KC", None)
    assert market_favorite(f) is None
    assert "No betting line posted" in render_fact_sheet(f)


def test_factor_lines_are_plain_english_and_flag_cross_season_windows(db):
    lines = _facts(db, "2026_01_BUF_KC", 2.5).factor_lines
    assert "Chiefs: betting market" in lines
    assert "Chiefs: season-long team strength rating" in lines
    epa = [line for line in lines if line.startswith("Bills: offensive efficiency")]
    assert len(epa) == 1 and "last season" in epa[0]
    assert len(lines) == 3  # week_number dropped
    assert not any("Elo" in line or "EPA" in line for line in lines)


def test_midseason_form(db):
    f = _facts(db, "2025_04_BUF_KC", 3.0)
    assert f.home.record == "3-0"
    assert f.home.last_game == "beat the Bills 24-17 at home"
    assert f.home.streak == "won 3 straight"
    assert f.away.last_game == "lost to the Chiefs 24-17 on the road"
    assert "allowing" in f.home.scoring


def test_sheet_holds_no_post_kickoff_facts(db):
    """Leakage: flipping the target game's own result changes nothing."""
    before = render_fact_sheet(_facts(db, "2025_04_BUF_KC", 3.0))
    game = db.get(Game, "2025_04_BUF_KC")
    game.home_score, game.away_score = 0, 55
    db.flush()
    assert render_fact_sheet(_facts(db, "2025_04_BUF_KC", 3.0)) == before
