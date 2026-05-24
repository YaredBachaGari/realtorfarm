"""Tests for the Bankruptcy collector."""
import os
from unittest.mock import patch

from realtorfarm.collectors.bankruptcy import collect_bankruptcy


# ── Fixtures ─────────────────────────────────────────────────────────────────

BURIEN_DOCKET = {
    "id": 12345678,
    "docket_number": "2:26-bk-00123",
    "case_name": "In re Jane Smith",
    "date_filed": "2026-05-20",
}

BURIEN_PARTIES = [
    {
        "name": "Jane Smith",
        "party_types": [{"name": "Debtor"}],
        "contact_information": [{
            "address1": "12345 6th Ave SW",
            "city": "Burien",
            "state": "WA",
            "zip_code": "98146",
        }],
    }
]

OUT_OF_AREA_PARTIES = [
    {
        "name": "John Doe",
        "party_types": [{"name": "Debtor"}],
        "contact_information": [{
            "address1": "999 Far Away St",
            "city": "Seattle",
            "state": "WA",
            "zip_code": "98101",  # not a Burien zip
        }],
    }
]

NO_ADDRESS_PARTIES = [
    {
        "name": "Bob Builder",
        "party_types": [{"name": "Debtor"}],
        "contact_information": [],  # no address data in CourtListener
    }
]


# ── Tests ────────────────────────────────────────────────────────────────────

def test_collect_bankruptcy_returns_empty_when_disabled():
    """BANKRUPTCY_ENABLED not set → returns ([], []) immediately."""
    assert os.environ.get("BANKRUPTCY_ENABLED", "") != "true"
    records, candidates = collect_bankruptcy(city="Burien", lookback_days=1)
    assert records == []
    assert candidates == []


def test_search_dockets_calls_courtlistener_once_per_chapter(monkeypatch):
    """collect_bankruptcy issues one search_dockets call per chapter (7, 11, 13)."""
    monkeypatch.setenv("BANKRUPTCY_ENABLED", "true")
    with patch("realtorfarm.collectors.bankruptcy.search_dockets", return_value=[]) as mock_search, \
         patch("realtorfarm.collectors.bankruptcy.time") as mock_time:
        mock_time.sleep = lambda _: None
        collect_bankruptcy(city="Burien", lookback_days=1)
    assert mock_search.call_count == 3
    chapters_searched = {c.kwargs["chapter"] for c in mock_search.call_args_list}
    assert chapters_searched == {7, 11, 13}


def test_parse_debtor_address_filters_to_target_city_zip(monkeypatch):
    """Debtor ZIP in Burien → candidate kept; out-of-area ZIP → discarded."""
    monkeypatch.setenv("BANKRUPTCY_ENABLED", "true")
    out_of_area_docket = {**BURIEN_DOCKET, "id": 99999, "docket_number": "2:26-bk-99999"}
    with patch("realtorfarm.collectors.bankruptcy.search_dockets",
               side_effect=[[BURIEN_DOCKET], [out_of_area_docket], []]), \
         patch("realtorfarm.collectors.bankruptcy.get_parties",
               side_effect=[BURIEN_PARTIES, OUT_OF_AREA_PARTIES]), \
         patch("realtorfarm.collectors.bankruptcy.time") as mock_time:
        mock_time.sleep = lambda _: None
        records, candidates = collect_bankruptcy(city="Burien", lookback_days=1)
    assert len(candidates) == 1
    assert "98146" in candidates[0]["property_address"]


def test_collect_bankruptcy_produces_candidate_with_missing_parcel(monkeypatch):
    """In-city debtor address → candidate with rejection_reason='missing_parcel_id'."""
    monkeypatch.setenv("BANKRUPTCY_ENABLED", "true")
    with patch("realtorfarm.collectors.bankruptcy.search_dockets",
               side_effect=[[BURIEN_DOCKET], [], []]), \
         patch("realtorfarm.collectors.bankruptcy.get_parties", return_value=BURIEN_PARTIES), \
         patch("realtorfarm.collectors.bankruptcy.time") as mock_time:
        mock_time.sleep = lambda _: None
        records, candidates = collect_bankruptcy(city="Burien", lookback_days=1)
    assert records == []
    assert len(candidates) == 1
    c = candidates[0]
    assert c["rejection_reason"] == "missing_parcel_id"
    assert c["case_id"] == "2:26-bk-00123"
    assert c["signals"] == ["Bankruptcy"]
    assert "Burien" in c["property_address"]
    assert "Chapter 7" in c["notes"]


def test_collect_bankruptcy_deduplicates_same_case_across_chapters(monkeypatch):
    """Same docket_number returned by multiple chapter queries → one candidate."""
    monkeypatch.setenv("BANKRUPTCY_ENABLED", "true")
    # All 3 chapter queries return the same docket
    with patch("realtorfarm.collectors.bankruptcy.search_dockets", return_value=[BURIEN_DOCKET]), \
         patch("realtorfarm.collectors.bankruptcy.get_parties", return_value=BURIEN_PARTIES), \
         patch("realtorfarm.collectors.bankruptcy.time") as mock_time:
        mock_time.sleep = lambda _: None
        records, candidates = collect_bankruptcy(city="Burien", lookback_days=1)
    case_ids = [c["case_id"] for c in candidates]
    assert case_ids.count("2:26-bk-00123") == 1


def test_collect_bankruptcy_skips_failed_chapter_and_continues(monkeypatch):
    """Chapter 7 raises RuntimeError → Chapters 11 and 13 still run; no crash."""
    monkeypatch.setenv("BANKRUPTCY_ENABLED", "true")
    search_side_effects = [
        RuntimeError("API timeout"),   # Chapter 7 fails
        [BURIEN_DOCKET],               # Chapter 11 succeeds
        [],                            # Chapter 13 empty
    ]
    with patch("realtorfarm.collectors.bankruptcy.search_dockets",
               side_effect=search_side_effects), \
         patch("realtorfarm.collectors.bankruptcy.get_parties", return_value=BURIEN_PARTIES), \
         patch("realtorfarm.collectors.bankruptcy.time") as mock_time:
        mock_time.sleep = lambda _: None
        records, candidates = collect_bankruptcy(city="Burien", lookback_days=1)
    assert isinstance(records, list)
    assert isinstance(candidates, list)
    assert any(c["case_id"] == "2:26-bk-00123" for c in candidates)


def test_collect_bankruptcy_sends_no_address_case_to_candidates(monkeypatch):
    """Case with no debtor address → candidate with rejection_reason='missing_debtor_address'."""
    monkeypatch.setenv("BANKRUPTCY_ENABLED", "true")
    with patch("realtorfarm.collectors.bankruptcy.search_dockets",
               side_effect=[[BURIEN_DOCKET], [], []]), \
         patch("realtorfarm.collectors.bankruptcy.get_parties", return_value=NO_ADDRESS_PARTIES), \
         patch("realtorfarm.collectors.bankruptcy.time") as mock_time:
        mock_time.sleep = lambda _: None
        records, candidates = collect_bankruptcy(city="Burien", lookback_days=1)
    assert len(candidates) == 1
    assert candidates[0]["rejection_reason"] == "missing_debtor_address"
    assert candidates[0]["case_id"] == "2:26-bk-00123"
