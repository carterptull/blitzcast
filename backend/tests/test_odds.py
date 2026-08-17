"""Odds ingestion. The stored spread follows nflverse convention (positive =
home favored) while books quote the opposite, so the sign is pinned here."""

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
