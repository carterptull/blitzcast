import pytest

from data_pipeline.team_names import CANONICAL_ABBRS, logo_url, nickname, to_abbr


def test_canonical_abbrs_pass_through():
    for abbr in CANONICAL_ABBRS:
        assert to_abbr(abbr) == abbr


def test_full_names_from_odds_api():
    assert to_abbr("Kansas City Chiefs") == "KC"
    assert to_abbr("Los Angeles Rams") == "LA"
    assert to_abbr("Washington Commanders") == "WAS"
    assert to_abbr("San Francisco 49ers") == "SF"


def test_alias_abbreviations():
    assert to_abbr("LAR") == "LA"
    assert to_abbr("WSH") == "WAS"
    assert to_abbr("JAC") == "JAX"
    assert to_abbr("OAK") == "LV"


def test_case_insensitive_full_names():
    assert to_abbr("kansas city chiefs") == "KC"


def test_unknown_name_raises():
    with pytest.raises(KeyError):
        to_abbr("London Monarchs")
    with pytest.raises(ValueError):
        to_abbr("")


def test_logo_url_slugs():
    assert logo_url("KC").endswith("/kc.png")
    assert logo_url("LA").endswith("/lar.png")
    assert logo_url("WAS").endswith("/wsh.png")


def test_nickname():
    assert nickname("Kansas City Chiefs") == "Chiefs"
    assert nickname("San Francisco 49ers") == "49ers"
