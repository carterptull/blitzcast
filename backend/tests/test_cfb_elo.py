"""CFB Elo config: MOV multiplier, FCS anchor, and NFL math unchanged."""

import math

import pytest

from ml import elo


def test_nfl_defaults_unchanged():
    assert elo.NFL_CONFIG == elo.EloConfig()
    assert elo.NFL_CONFIG.k == 20.0
    assert elo.NFL_CONFIG.hfa == 55.0
    assert elo.NFL_CONFIG.season_regression == 0.75
    assert elo.NFL_CONFIG.mov is False
    assert elo.expected_home(1500, 1500) == pytest.approx(1 / (1 + 10 ** (-55 / 400)))


def test_nfl_update_ignores_margin():
    plain = elo.update(1500, 1600, 1.0)
    with_margin = elo.update(1500, 1600, 1.0, margin=45)
    assert plain == with_margin


def test_cfb_config_values():
    cfg = elo.config_for("CFB")
    assert cfg is elo.CFB_CONFIG
    assert cfg.hfa == 65.0
    assert cfg.season_regression == 0.50
    assert cfg.mov is True
    assert cfg.margin_cap == 28
    assert cfg.fcs_offset == 350.0
    assert elo.config_for("NFL") is elo.NFL_CONFIG


def test_mov_multiplier_formula_and_cap():
    cfg = elo.CFB_CONFIG
    # Even matchup (winner advantage 0): multiplier is ln(margin+1).
    assert elo.mov_multiplier(14, 0.0, cfg) == pytest.approx(math.log(15))
    # 56-point cupcake win is capped at 28 before the log.
    assert elo.mov_multiplier(56, 0.0, cfg) == pytest.approx(math.log(29))
    # Damped for a heavy favorite, boosted for an upset winner.
    assert elo.mov_multiplier(14, 200.0, cfg) < elo.mov_multiplier(14, -200.0, cfg)
    assert elo.mov_multiplier(14, 200.0, cfg) == pytest.approx(
        math.log(15) * (2.2 / (200.0 * 0.001 + 2.2))
    )


def test_cfb_update_applies_mov():
    cfg = elo.CFB_CONFIG
    exp = elo.expected_home(1500, 1500, cfg)
    mult = elo.mov_multiplier(21, (1500 + cfg.hfa) - 1500, cfg)
    home, away = elo.update(1500, 1500, 1.0, cfg, margin=21)
    assert home - 1500 == pytest.approx(cfg.k * (1.0 - exp) * mult)
    assert home + away == pytest.approx(3000)


def test_cfb_update_mov_for_away_winner_uses_away_advantage():
    cfg = elo.CFB_CONFIG
    exp = elo.expected_home(1500, 1500, cfg)
    away_adv = -((1500 + cfg.hfa) - 1500)
    mult = elo.mov_multiplier(-10, away_adv, cfg)
    home, away = elo.update(1500, 1500, 0.0, cfg, margin=-10)
    assert 1500 - home == pytest.approx(cfg.k * exp * mult)


def test_fcs_anchor_first_appearance():
    book = elo.EloBook(config=elo.CFB_CONFIG, tiers={"MERC": "FCS"})
    fbs, fcs = book.pre_game(2025, "UGA", "MERC")
    assert fbs == 1500.0
    assert fcs == 1150.0


def test_fcs_anchor_on_season_rollover():
    book = elo.EloBook(config=elo.CFB_CONFIG, tiers={"MERC": "FCS"})
    book.ratings.update({"UGA": 1700.0, "MERC": 1300.0})
    book.current_season = 2024
    uga, merc = book.pre_game(2025, "UGA", "MERC")
    # FBS regresses toward 1500; FCS regresses toward its 1150 anchor.
    assert uga == pytest.approx(1500 + 0.5 * (1700 - 1500))
    assert merc == pytest.approx(1150 + 0.5 * (1300 - 1150))


def test_nfl_book_defaults_match_legacy_behavior():
    book = elo.EloBook()
    book.record_result(2024, "KC", "BUF", 30, 20)
    kc = book.ratings["KC"]
    exp = elo.expected_home(1500, 1500)
    assert kc == pytest.approx(1500 + 20.0 * (1.0 - exp))
    kc_pre, _ = book.pre_game(2025, "KC", "BUF")
    assert kc_pre == pytest.approx(elo.regress_to_mean(kc))
