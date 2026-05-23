from unittest.mock import patch
from realtorfarm.collectors.parcel_enrichment import enrich_candidates


CANDIDATE_MISSING_PARCEL = {
    "source_url": "https://example.com/notice",
    "target_city": "Kent",
    "signals": ["NOTS"],
    "property_address": "310 W Meeker St, Kent, WA 98032",
    "parcel_id": "",
    "case_id": "KENT-2026-0100",
    "recorded_date": "2026-05-20",
    "rejection_reason": "missing_parcel_id",
    "enrichment_needed": True,
}

CANDIDATE_MISSING_ADDRESS = {
    "source_url": "https://example.com/notice2",
    "target_city": "Kent",
    "signals": ["NOTS"],
    "property_address": "",
    "parcel_id": "232204-9001",
    "case_id": "",
    "recorded_date": "2026-05-20",
    "rejection_reason": "missing_target_city_property_address",
    "enrichment_needed": True,
}

CANDIDATE_WRONG_REJECTION = {
    "source_url": "https://example.com/notice3",
    "target_city": "Kent",
    "signals": [],
    "property_address": "",
    "parcel_id": "",
    "case_id": "",
    "recorded_date": "2026-05-20",
    "rejection_reason": "missing_distress_signal",
    "enrichment_needed": True,
}

PARCEL_VIEWER_RESULT_WITH_PARCEL = "Parcel Account Number: 232204-9010\nSitus Address: 310 W Meeker St, Kent, WA 98032\nOwner: KENT TEST LLC"
PARCEL_VIEWER_RESULT_WITH_ADDRESS = "Situs Address: 220 4th Ave S, Kent, WA 98032\nParcel Account Number: 232204-9001\nOwner: KENT SAMPLE OWNER LLC"


def test_enrichment_fills_parcel_for_candidate_missing_parcel():
    with patch("realtorfarm.collectors.parcel_enrichment.run_task", return_value=PARCEL_VIEWER_RESULT_WITH_PARCEL):
        records = enrich_candidates([CANDIDATE_MISSING_PARCEL], city="Kent", max_enrichments=10)

    assert len(records) == 1
    assert records[0]["parcel_id"] != ""
    assert records[0]["signal"] == "NOTS"


def test_enrichment_fills_address_for_candidate_missing_address():
    with patch("realtorfarm.collectors.parcel_enrichment.run_task", return_value=PARCEL_VIEWER_RESULT_WITH_ADDRESS):
        records = enrich_candidates([CANDIDATE_MISSING_ADDRESS], city="Kent", max_enrichments=10)

    assert len(records) == 1
    assert "Kent" in records[0]["property_address"]
    assert records[0]["parcel_id"] == "232204-9001"


def test_enrichment_skips_wrong_rejection_reason():
    with patch("realtorfarm.collectors.parcel_enrichment.run_task") as mock_bu:
        records = enrich_candidates([CANDIDATE_WRONG_REJECTION], city="Kent", max_enrichments=10)

    mock_bu.assert_not_called()
    assert records == []


def test_enrichment_respects_max_cap():
    candidates = [CANDIDATE_MISSING_PARCEL] * 20

    with patch("realtorfarm.collectors.parcel_enrichment.run_task", return_value=PARCEL_VIEWER_RESULT_WITH_PARCEL) as mock_bu:
        records = enrich_candidates(candidates, city="Kent", max_enrichments=3)

    assert mock_bu.call_count == 3
    assert len(records) == 3


def test_enrichment_returns_empty_on_zero_cap():
    with patch("realtorfarm.collectors.parcel_enrichment.run_task") as mock_bu:
        records = enrich_candidates([CANDIDATE_MISSING_PARCEL], city="Kent", max_enrichments=0)

    mock_bu.assert_not_called()
    assert records == []


def test_enrichment_skips_candidate_on_browser_use_failure():
    with patch("realtorfarm.collectors.parcel_enrichment.run_task", side_effect=Exception("timeout")):
        records = enrich_candidates([CANDIDATE_MISSING_PARCEL], city="Kent", max_enrichments=10)

    assert records == []
