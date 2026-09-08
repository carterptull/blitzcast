"""CFBD ingestion: the -100000 'no real price quoted' sentinel must not be
stored as a genuine moneyline (see cfb_401856665, a 57-0 game where both
sides came back -100000, which corrupted market_home_prob toward 0.5)."""
from unittest.mock import patch

from data_pipeline.cfbd import _real_moneyline, load_lines


def test_real_moneyline_passes_through_genuine_prices():
    assert _real_moneyline(-1725) == -1725
    assert _real_moneyline(900) == 900
    assert _real_moneyline(None) is None


def test_real_moneyline_filters_no_quote_sentinel():
    assert _real_moneyline(-100000) is None
    assert _real_moneyline(100000) is None


def test_load_lines_filters_sentinel_from_api_response():
    fake_response = [
        {
            "id": "cfb_401856665",
            "lines": [
                {
                    "provider": "consensus",
                    "spread": -30.0,
                    "overUnder": 55.0,
                    "homeMoneyline": -100000,
                    "awayMoneyline": -100000,
                }
            ],
        }
    ]
    with patch("data_pipeline.cfbd._get", return_value=fake_response):
        df = load_lines(2026)
    row = df.iloc[0]
    assert row["home_moneyline"] is None
    assert row["away_moneyline"] is None
