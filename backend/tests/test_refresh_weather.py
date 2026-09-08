"""Neutral-site games (no Team-derived stadium) must not be silently
skipped the same way domes are — they should be fetched by venue name."""
from unittest.mock import patch

from data_pipeline.refresh_weather import fetch_day


def test_fetch_day_accepts_lat_lon_string():
    with patch("data_pipeline.refresh_weather.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"days": []}
        mock_get.return_value.raise_for_status.return_value = None
        fetch_day("33.9535,-118.3392", "2026-09-10", "key")
        url = mock_get.call_args[0][0]
        assert "33.9535,-118.3392" in url


def test_fetch_day_accepts_venue_name_string():
    with patch("data_pipeline.refresh_weather.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"days": []}
        mock_get.return_value.raise_for_status.return_value = None
        fetch_day("Melbourne Cricket Ground", "2026-09-10", "key")
        url = mock_get.call_args[0][0]
        assert "Melbourne Cricket Ground" in url
