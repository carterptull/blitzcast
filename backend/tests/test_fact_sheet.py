from datetime import UTC, date, datetime

from sqlalchemy import select

from app.models import Game, Injury, Team, Weather
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


def _build(db, game_id, spread=2.5, factors=FACTORS, ranks=None, prev_ranks=None):
    game = db.get(Game, game_id)
    return build_game_facts(
        db, game, 0.61, factors, spread_home=spread, ranks=ranks, prev_ranks=prev_ranks
    )


def _team_id(db, abbr, sport="NFL"):
    return db.scalar(select(Team.team_id).where(Team.abbr == abbr, Team.sport == sport))


def _add_game(db, game_id, home, away, *, season=2026, week=1, when, scores=(24, 17),
              sport="NFL"):
    home_id, away_id = _team_id(db, home, sport), _team_id(db, away, sport)
    db.add(
        Game(
            game_id=game_id, sport=sport, season=season, week=week,
            game_date=when.date(), kickoff_time=when,
            home_team_id=home_id, away_team_id=away_id,
            is_primetime=False, is_divisional=False,
            home_score=scores[0] if scores else None,
            away_score=scores[1] if scores else None,
            status="final" if scores else "scheduled",
        )
    )
    db.flush()


# Important 1: market factor line follows the posted spread

def test_pickem_spread_emits_no_market_factor_line(db):
    f = _build(db, "2026_01_BUF_KC", spread=0.0, factors=[_factor("market_spread_home", "away")])
    assert f.factor_lines == ()
    assert "a pick'em" in render_fact_sheet(f)


def test_market_factor_names_the_spread_favorite_not_the_shap_direction(db):
    away_fav = _build(
        db, "2026_01_BUF_KC", spread=-3.0, factors=[_factor("market_spread_home", "home")]
    )
    assert away_fav.factor_lines == ("Bills: betting market",)
    home_fav = _build(
        db, "2026_01_BUF_KC", spread=3.0, factors=[_factor("market_home_prob", "away")]
    )
    assert home_fav.factor_lines == ("Chiefs: betting market",)


def test_market_factor_omitted_without_a_line(db):
    f = _build(db, "2026_01_BUF_KC", spread=None, factors=[_factor("market_spread_home", "home")])
    assert f.factor_lines == ()


def test_away_favored_market_line_wording(db):
    sheet = render_fact_sheet(_build(db, "2026_01_BUF_KC", spread=-3.5))
    assert "Betting market: Bills favored by 3.5 points (BUF -3.5, KC +3.5)" in sheet


# Important 2: CFB rank lines depend on whether a poll exists

CFB_GAME = "cfb_401800001"


def test_cfb_without_poll_data_prints_no_rank_line(db):
    f = _build(db, CFB_GAME, spread=None, factors=[], ranks={})
    assert f.poll_available is False
    assert "AP rank" not in render_fact_sheet(f)


def test_cfb_team_absent_from_a_real_poll_is_unranked(db):
    uga = _team_id(db, "UGA", "CFB")
    f = _build(db, CFB_GAME, spread=None, factors=[], ranks={uga: 3})
    assert f.poll_available is True
    sheet = render_fact_sheet(f)
    assert sheet.count("- AP rank: unranked") == 1
    assert "- AP rank: #3" in sheet


def test_cfb_rank_note_with_previous_poll(db):
    uga, ala = _team_id(db, "UGA", "CFB"), _team_id(db, "ALA", "CFB")
    f = _build(
        db, CFB_GAME, spread=None, factors=[], ranks={uga: 3, ala: 7}, prev_ranks={uga: 5}
    )
    sheet = render_fact_sheet(f)
    assert "- AP rank: #3, up from #5" in sheet
    assert "- AP rank: #7, new to the poll this week" in sheet


def test_cfb_full_name_uses_mascot_and_lists_no_injuries(db):
    ala = db.get(Game, CFB_GAME).home_team
    ala.mascot = "Crimson Tide"
    db.add(
        Injury(
            game_id=CFB_GAME, team_id=ala.team_id, player_name="Some Player",
            position="QB", status="Out", report_date=date(2026, 9, 3),
        )
    )
    db.flush()
    f = _build(db, CFB_GAME, spread=None, factors=[])
    assert f.home.full_name == "Alabama Crimson Tide"
    assert f.home.injuries == () and f.away.injuries == ()


# Weather

def _add_weather(db, captured_at, **kw):
    db.add(Weather(game_id="2026_01_BUF_KC", captured_at=captured_at, **kw))
    db.flush()


def test_weather_omits_unknown_wind(db):
    _add_weather(db, datetime(2026, 9, 12, 12, 0, tzinfo=UTC), temp_f=70.0, wind_mph=None)
    assert _build(db, "2026_01_BUF_KC").weather == "70 degrees"


def test_weather_keeps_a_pre_kickoff_forecast(db):
    _add_weather(
        db, datetime(2026, 9, 12, 12, 0, tzinfo=UTC), temp_f=70.0, wind_mph=8.0,
        precipitation=True,
    )
    assert _build(db, "2026_01_BUF_KC").weather == "70 degrees, wind 8 mph, rain or snow likely"


def test_weather_ignores_a_post_kickoff_capture(db):
    _add_weather(db, datetime(2026, 9, 13, 17, 0, tzinfo=UTC), temp_f=70.0, wind_mph=8.0)
    assert _build(db, "2026_01_BUF_KC").weather is None


# Injuries

def test_injuries_include_doubtful_exclude_questionable_and_handle_missing_position(db):
    buf = _team_id(db, "BUF")
    for name, pos, status in (
        ("Quest Guy", "WR", "Questionable"),
        ("Doubt Guy", "RB", "Doubtful"),
        ("Nopos Guy", None, "Out"),
    ):
        db.add(
            Injury(
                game_id="2026_01_BUF_KC", team_id=buf, player_name=name, position=pos,
                status=status, report_date=date(2026, 9, 11),
            )
        )
    db.flush()
    injuries = _build(db, "2026_01_BUF_KC").away.injuries
    assert "Doubt Guy (RB) is listed Doubtful" in injuries
    assert "Nopos Guy is listed Out" in injuries
    assert not any("Quest Guy" in i or "None" in i for i in injuries)


# Last meeting

def test_postseason_last_meeting_wording(db):
    _add_game(db, "2025_19_BUF_KC", "KC", "BUF", season=2025, week=19,
              when=datetime(2026, 1, 25, 20, 0, tzinfo=UTC), scores=(27, 20))
    assert _build(db, "2026_01_BUF_KC").last_meeting == "Chiefs won 27-20 in the 2025 postseason"


def test_cfb_postseason_last_meeting_wording(db):
    _add_game(db, "cfb_prior", "ALA", "UGA", season=2025, week=16, sport="CFB",
              when=datetime(2026, 1, 8, 20, 0, tzinfo=UTC), scores=(30, 27))
    f = _build(db, CFB_GAME, spread=None, factors=[])
    assert f.last_meeting == "Alabama won 30-27 in the 2025 postseason"


# Result phrases

def test_neutral_site_and_tie_result_phrases(db):
    wk3 = db.get(Game, "2025_03_BUF_KC")
    wk3.is_neutral_site = True
    db.flush()
    assert _build(db, "2025_04_BUF_KC").home.last_game == "beat the Bills 24-17 at a neutral site"
    wk3.home_score = wk3.away_score = 20
    db.flush()
    assert _build(db, "2025_04_BUF_KC").home.last_game == "tied the Bills 20-20 at a neutral site"


# Rest

def test_short_week_and_bye(db):
    _add_game(db, "2026_00_PHI_KC", "KC", "PHI", week=0,
              when=datetime(2026, 9, 9, 17, 0, tzinfo=UTC))
    assert _build(db, "2026_01_BUF_KC").home.rest == "on a short week"
    prior = db.get(Game, "2026_00_PHI_KC")
    prior.kickoff_time = datetime(2026, 8, 30, 17, 0, tzinfo=UTC)
    prior.game_date = prior.kickoff_time.date()
    db.flush()
    assert _build(db, "2026_01_BUF_KC").home.rest == "coming off a bye"


def test_rest_ignores_unfinished_previous_games(db):
    _add_game(db, "2026_00_PHI_KC", "KC", "PHI", week=0,
              when=datetime(2026, 9, 9, 17, 0, tzinfo=UTC), scores=None)
    assert _build(db, "2026_01_BUF_KC").home.rest is None
