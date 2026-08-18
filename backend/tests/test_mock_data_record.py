"""Coverage for mock_data.get_record -- the mock-mode sibling of the real
/api/record logic in services/predictions.py. Same verdict-grading and
pick'em-exclusion rules, no DB involved."""

from app import mock_data as md


def test_get_record_wrong_season_returns_empty_insufficient():
    """The early-return branch: a season that isn't MOCK_SEASON yields an
    empty, insufficient record rather than touching the fixture games."""
    body = md.get_record(md.MOCK_SEASON - 1, "NFL")
    assert body.total == 0
    assert body.correct == 0
    assert body.market_correct == 0
    assert body.sufficient is False


def test_get_record_mock_season_has_expected_shape():
    """Sanity check on the happy path: the real MOCK_SEASON produces a
    RecordOut with sport/season echoed back and a gradeable (if small)
    sample from the fixture games."""
    body = md.get_record(md.MOCK_SEASON, "NFL")
    assert body.sport == "NFL"
    assert body.season == md.MOCK_SEASON
    assert body.total > 0
    assert body.market_correct <= body.total
    assert body.correct <= body.total


def test_get_record_below_ten_graded_games_is_insufficient():
    """The fixture data naturally produces far fewer than 10 graded games
    (NFL + CFB combined), so `sufficient` must be False -- exercising the
    total >= 10 threshold without fixture surgery."""
    body = md.get_record(md.MOCK_SEASON)
    assert body.total < 10
    assert body.sufficient is False


def test_get_record_excludes_pickem_market_lines_from_both_counts(monkeypatch):
    """Mirrors test_record.py's regression test for the real endpoint: a
    pick'em market line (symmetric -110/-110, de-vigs to exactly 0.5) must
    drop the game from both `total` and `market_correct` entirely, not get
    scored as a market loss -- even though the model's own prediction on
    that same game is gradeable."""
    game = md._MOCK_GAMES[0]  # 2026_01_BUF_KC: has scores, prob, and odds
    assert game["home_win_prob"] is not None
    assert game["home_score"] is not None and game["away_score"] is not None

    baseline = md.get_record(md.MOCK_SEASON, "NFL")

    monkeypatch.setitem(game, "odds", {"moneyline_home": -110, "moneyline_away": -110})
    pickem = md.get_record(md.MOCK_SEASON, "NFL")

    assert pickem.total == baseline.total - 1
    assert pickem.market_correct == 0
    assert pickem.correct == 0  # this game was the only gradeable "correct" one
