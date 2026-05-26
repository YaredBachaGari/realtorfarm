# tests/test_collectors_parcel_enrichment.py
from unittest.mock import patch, MagicMock
from realtorfarm.collectors.parcel_enrichment import enrich_candidates


def _mock_gis(pin, addr, city="KENT", zip5="98032"):
    m = MagicMock()
    m.raise_for_status.return_value = None
    m.json.return_value = {
        "features": [{"attributes": {"PIN": pin, "ADDR_FULL": addr, "CTYNAME": city, "ZIP5": zip5}}]
    }
    return m


def _mock_gis_empty():
    m = MagicMock()
    m.raise_for_status.return_value = None
    m.json.return_value = {"features": []}
    return m


CANDIDATE_MISSING_PARCEL = {
    "source_url": "https://example.com/notice",
    "signals": ["NOTS"],
    "property_address": "310 W Meeker St, Kent, WA 98032",
    "parcel_id": "",
    "case_id": "KENT-2026-0100",
    "recorded_date": "2026-05-20",
    "rejection_reason": "missing_parcel_id",
}

CANDIDATE_MISSING_ADDRESS = {
    "source_url": "https://example.com/notice2",
    "signals": ["NOTS"],
    "property_address": "",
    "parcel_id": "232204-9001",
    "case_id": "",
    "recorded_date": "2026-05-20",
    "rejection_reason": "missing_target_city_property_address",
}

CANDIDATE_WRONG_REJECTION = {
    "signals": [],
    "property_address": "",
    "parcel_id": "",
    "rejection_reason": "missing_distress_signal",
}


def test_enrichment_fills_parcel_for_candidate_missing_parcel():
    with patch("realtorfarm.collectors.kc_gis.requests.get",
               return_value=_mock_gis("2322049010", "310 W MEEKER ST")):
        records = enrich_candidates([CANDIDATE_MISSING_PARCEL], city="Kent", max_enrichments=10)
    assert len(records) == 1
    assert records[0]["parcel_id"] == "232204-9010"
    assert "Meeker" in records[0]["property_address"]
    assert records[0]["signal"] == "NOTS"


def test_enrichment_fills_address_for_candidate_missing_address():
    with patch("realtorfarm.collectors.kc_gis.requests.get",
               return_value=_mock_gis("2322049001", "220 4TH AVE S")):
        records = enrich_candidates([CANDIDATE_MISSING_ADDRESS], city="Kent", max_enrichments=10)
    assert len(records) == 1
    assert "Kent" in records[0]["property_address"]
    assert records[0]["parcel_id"] == "232204-9001"


def test_enrichment_skips_wrong_rejection_reason():
    with patch("realtorfarm.collectors.kc_gis.requests.get") as mock_get:
        records = enrich_candidates([CANDIDATE_WRONG_REJECTION], city="Kent", max_enrichments=10)
    mock_get.assert_not_called()
    assert records == []


def test_enrichment_respects_max_cap():
    candidates = [CANDIDATE_MISSING_PARCEL] * 20
    with patch("realtorfarm.collectors.kc_gis.requests.get",
               return_value=_mock_gis("2322049010", "310 W MEEKER ST")) as mock_get:
        records = enrich_candidates(candidates, city="Kent", max_enrichments=3)
    assert mock_get.call_count == 3
    assert len(records) == 3


def test_enrichment_returns_empty_on_zero_cap():
    with patch("realtorfarm.collectors.kc_gis.requests.get") as mock_get:
        records = enrich_candidates([CANDIDATE_MISSING_PARCEL], city="Kent", max_enrichments=0)
    mock_get.assert_not_called()
    assert records == []


def test_enrichment_skips_candidate_on_api_failure():
    with patch("realtorfarm.collectors.kc_gis.requests.get", side_effect=Exception("timeout")):
        records = enrich_candidates([CANDIDATE_MISSING_PARCEL], city="Kent", max_enrichments=10)
    assert records == []


def test_enrichment_skips_candidate_when_api_returns_no_match():
    with patch("realtorfarm.collectors.kc_gis.requests.get", return_value=_mock_gis_empty()):
        records = enrich_candidates([CANDIDATE_MISSING_PARCEL], city="Kent", max_enrichments=10)
    assert records == []
