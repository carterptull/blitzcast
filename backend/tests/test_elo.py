import pytest

from ml import elo


def test_expected_home_even_teams_has_hfa():
    exp = elo.expected_home(1500, 1500)
    assert exp > 0.5
    assert exp == pytest.approx(1 / (1 + 10 ** (-55 / 400)))


def test_update_is_zero_sum():
    home, away = elo.update(1500, 1600, 1.0)
    assert home + away == pytest.approx(3100)
    assert home > 1500
    assert away < 1600


def test_update_favors_upset_more():
    _, _ = elo.update(1700, 1400, 1.0)
    favorite_gain = elo.update(1700, 1400, 1.0)[0] - 1700
    underdog_gain = elo.update(1400, 1700, 1.0)[0] - 1400
    assert underdog_gain > favorite_gain


def test_tie_moves_ratings_toward_each_other():
    home, away = elo.update(1600, 1500, 0.5)
    assert home < 1600
    assert away > 1500


def test_season_regression():
    assert elo.regress_to_mean(1700) == pytest.approx(1650)
    assert elo.regress_to_mean(1300) == pytest.approx(1350)
    assert elo.regress_to_mean(1500) == pytest.approx(1500)


def test_book_replay_and_season_rollover():
    book = elo.EloBook()
    book.record_result(2024, "KC", "BUF", 30, 20)
    kc_2024 = book.ratings["KC"]
    assert kc_2024 > 1500

    kc_pre, _ = book.pre_game(2025, "KC", "BUF")
    assert kc_pre == pytest.approx(elo.regress_to_mean(kc_2024))
