from unittest.mock import patch, MagicMock
from realtorfarm.collectors.kc_gis import (
    lookup_by_pin,
    lookup_by_address,
    pin_to_formatted,
    format_address,
    _normalize_street,
)


def _mock_gis(features):
    m = MagicMock()
    m.raise_for_status.return_value = None
    m.json.return_value = {"features": features}
    return m


def _feature(pin, addr, city, zip5):
    return {"attributes": {"PIN": pin, "ADDR_FULL": addr, "CTYNAME": city, "ZIP5": zip5}}


def test_pin_to_formatted_with_dash():
    assert pin_to_formatted("232204-9055") == "232204-9055"

def test_pin_to_formatted_without_dash():
    assert pin_to_formatted("2322049055") == "232204-9055"

def test_pin_to_formatted_pads_short_pin():
    assert pin_to_formatted("12345") == "000001-2345"

def test_format_address_builds_full_string():
    attrs = {"ADDR_FULL": "415 W GOWE ST", "CTYNAME": "KENT", "ZIP5": "98032"}
    assert format_address(attrs) == "415 W Gowe St, Kent, WA 98032"

def test_format_address_missing_zip():
    attrs = {"ADDR_FULL": "415 W GOWE ST", "CTYNAME": "KENT", "ZIP5": ""}
    assert format_address(attrs) == "415 W Gowe St, Kent, WA"

def test_format_address_missing_city():
    attrs = {"ADDR_FULL": "415 W GOWE ST", "CTYNAME": "", "ZIP5": "98032"}
    assert format_address(attrs) == "415 W Gowe St, WA 98032"

def test_normalize_street_strips_city():
    assert _normalize_street("415 W Gowe St, Kent, WA 98032") == "415 W GOWE ST"

def test_normalize_street_expands_long_type():
    assert _normalize_street("310 W Meeker Street, Kent, WA") == "310 W MEEKER ST"

def test_normalize_street_escapes_single_quote():
    assert "O''BRIEN" in _normalize_street("123 O'Brien Ave")

def test_lookup_by_pin_returns_attributes():
    feat = _feature("2322049055", "415 W GOWE ST", "KENT", "98032")
    with patch("realtorfarm.collectors.kc_gis.requests.get", return_value=_mock_gis([feat])) as mock_get:
        result = lookup_by_pin("232204-9055")
    assert result == feat["attributes"]
    called_params = mock_get.call_args[1]["params"]
    assert "2322049055" in called_params["where"]

def test_lookup_by_pin_returns_none_on_empty():
    with patch("realtorfarm.collectors.kc_gis.requests.get", return_value=_mock_gis([])):
        assert lookup_by_pin("000000-0000") is None

def test_lookup_by_address_returns_first_match():
    feat = _feature("2322049055", "415 W GOWE ST", "KENT", "98032")
    with patch("realtorfarm.collectors.kc_gis.requests.get", return_value=_mock_gis([feat])):
        result = lookup_by_address("415 W Gowe St, Kent, WA 98032")
    assert result == feat["attributes"]

def test_lookup_by_address_returns_none_on_empty():
    with patch("realtorfarm.collectors.kc_gis.requests.get", return_value=_mock_gis([])):
        assert lookup_by_address("999 Nowhere St, Kent, WA 98032") is None


def test_lookup_by_pin_raises_on_invalid_pin():
    import pytest
    with pytest.raises(ValueError, match="Invalid KC PIN"):
        lookup_by_pin("not-a-pin")


def test_pin_to_formatted_raises_on_too_long():
    import pytest
    with pytest.raises(ValueError, match="too long"):
        pin_to_formatted("12345678901")  # 11 digits


def test_lookup_by_pin_raises_on_api_error_response():
    import pytest
    m = MagicMock()
    m.raise_for_status.return_value = None
    m.json.return_value = {"error": {"code": 400, "message": "Invalid query"}}
    with patch("realtorfarm.collectors.kc_gis.requests.get", return_value=m):
        with pytest.raises(RuntimeError, match="KC GIS API error"):
            lookup_by_pin("232204-9055")


def test_normalize_street_does_not_corrupt_mid_name_type_word():
    # "BOULEVARD PARK DR" - BOULEVARD is part of the name, not the suffix
    result = _normalize_street("310 Boulevard Park Dr, Kent, WA 98032")
    assert result == "310 BOULEVARD PARK DR"  # BOULEVARD should NOT be replaced, trailing DR must be present


def test_lookup_by_address_raises_on_api_error_response():
    import pytest
    m = MagicMock()
    m.raise_for_status.return_value = None
    m.json.return_value = {"error": {"code": 400, "message": "Invalid query"}}
    with patch("realtorfarm.collectors.kc_gis.requests.get", return_value=m):
        with pytest.raises(RuntimeError, match="KC GIS API error"):
            lookup_by_address("123 Main St")
