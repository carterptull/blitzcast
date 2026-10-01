"""Odds ingestion. The stored spread follows nflverse convention (positive =
home favored) while books quote the opposite, so the sign is pinned here."""

import sys

import pytest
import requests

from app.market import plausible_moneylines, real_moneyline
from data_pipeline import refresh_odds
from data_pipeline.refresh_odds import _consensus, book_spread_to_home


def _event(home_point: float, home_price: int, away_price: int) -> dict:
    return {
        "home_team": "Kansas City Chiefs",
        "away_team": "Buffalo Bills",
        "bookmakers": [
            {
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Kansas City Chiefs", "price": home_price},
                            {"name": "Buffalo Bills", "price": away_price},
                        ],
                    },
                    {
                        "key": "spreads",
                        "outcomes": [
                            {"name": "Kansas City Chiefs", "point": home_point},
                            {"name": "Buffalo Bills", "point": -home_point},
                        ],
                    },
                    {
                        "key": "totals",
                        "outcomes": [
                            {"name": "Over", "point": 48.5, "price": -110},
                            {"name": "Under", "point": 48.5, "price": -110},
                        ],
                    },
                ]
            }
        ],
    }


def test_book_spread_sign_flips_to_home_convention():
    assert book_spread_to_home(-7.5) == 7.5
    assert book_spread_to_home(3.0) == -3.0
    assert book_spread_to_home(0) == 0.0


def test_home_favorite_stores_a_positive_spread():
    """Book quotes the home favorite at -7.5; storage keeps +7.5."""
    markets = _consensus(_event(-7.5, -330, 260), "KC", "BUF")
    assert markets["spreads"] == -7.5
    assert book_spread_to_home(markets["spreads"]) == 7.5


def test_away_favorite_stores_a_negative_spread():
    markets = _consensus(_event(4.5, 170, -200), "KC", "BUF")
    assert book_spread_to_home(markets["spreads"]) == -4.5


def test_stored_spread_agrees_with_the_moneyline_favorite():
    """The two market signals must never disagree about who is favored."""
    for home_point, home_price, away_price in [
        (-7.5, -330, 260),
        (-2.5, -140, 120),
        (4.5, 170, -200),
        (10.0, 380, -500),
    ]:
        markets = _consensus(_event(home_point, home_price, away_price), "KC", "BUF")
        spread_says_home = book_spread_to_home(markets["spreads"]) > 0
        moneyline_says_home = home_price < away_price
        assert spread_says_home == moneyline_says_home


def test_consensus_reads_h2h_and_totals():
    markets = _consensus(_event(-7.5, -330, 260), "KC", "BUF")
    assert markets["h2h"] == (-330, 260)
    assert markets["totals"] == 48.5


def test_real_moneyline_drops_sentinel():
    assert real_moneyline(-100000) is None
    assert real_moneyline(100000) is None
    assert real_moneyline(-8000) == -8000
    assert real_moneyline(None) is None


def test_plausible_moneylines():
    assert plausible_moneylines(-108, -112)        # pick'em vig
    assert plausible_moneylines(-10000, 2400)      # real blowout
    assert not plausible_moneylines(-100000, -100000)
    assert not plausible_moneylines(-5000, -5000)  # implied sum ~1.96
    assert not plausible_moneylines(None, 150)


def test_consensus_skips_a_sentinel_book_for_the_next_one():
    event = {
        "home_team": "Rutgers Scarlet Knights", "away_team": "Howard Bison",
        "bookmakers": [
            {"markets": [{"key": "h2h", "outcomes": [
                {"name": "Rutgers Scarlet Knights", "price": -100000},
                {"name": "Howard Bison", "price": -100000},
            ]}]},
            {"markets": [{"key": "h2h", "outcomes": [
                {"name": "Rutgers Scarlet Knights", "price": -20000},
                {"name": "Howard Bison", "price": 3500},
            ]}]},
        ],
    }
    assert _consensus(event, "RUTG", "HOW")["h2h"] == (-20000, 3500)


def test_odds_http_error_is_redacted_and_exits_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(refresh_odds.get_settings(), "odds_api_key", "SECRETKEY")
    monkeypatch.setattr(sys, "argv", ["refresh_odds", "--sport", "nfl"])

    def boom(*args, **kwargs):
        raise requests.HTTPError("401 Client Error for url: https://x/odds?apiKey=SECRETKEY")

    def no_db(*args, **kwargs):
        raise AssertionError("must exit before opening a DB session")

    monkeypatch.setattr(refresh_odds.requests, "get", boom)
    monkeypatch.setattr(refresh_odds, "session_scope", no_db)
    with pytest.raises(SystemExit) as exc:
        refresh_odds.main()
    assert exc.value.code == 1
    out = capsys.readouterr()
    assert "SECRETKEY" not in out.out + out.err
    assert "HTTPError" in out.out
