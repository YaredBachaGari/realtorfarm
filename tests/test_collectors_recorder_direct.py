import os
from unittest.mock import patch
from realtorfarm.collectors.recorder_direct import collect_recorder_direct


LANDMARK_NOTS_WITH_PARCEL = """
Recording Date: 2026-05-22
Recording Number: 20260522000456
Grantor: BURIEN SAMPLE OWNER LLC
Property Address: 12345 6th Ave SW, Burien, WA 98146
Parcel: 123450-0678
Document Type: NOTICE OF TRUSTEE SALE
"""

LANDMARK_NOD_MISSING_PARCEL = """
Recording Date: 2026-05-21
Recording Number: 20260521000789
Grantor: ANOTHER OWNER LLC
Property Address: 999 SW 152nd St, Burien, WA 98166
Document Type: NOTICE OF DEFAULT
"""


def test_collect_recorder_direct_returns_empty_when_disabled():
    records, candidates = collect_recorder_direct(city="Burien", lookback_days=1)
    assert records == []
    assert candidates == []


def test_collect_recorder_direct_runs_one_task_per_doc_type(monkeypatch):
    monkeypatch.setenv("RECORDER_DIRECT_ENABLED", "true")
    with patch("realtorfarm.collectors.recorder_direct.run_task", return_value="") as mock_run:
        collect_recorder_direct(city="Burien", lookback_days=1)
    assert mock_run.call_count == 3
    calls_text = " ".join(str(c) for c in mock_run.call_args_list)
    assert "NOTICE OF TRUSTEE SALE" in calls_text
    assert "NOTICE OF DEFAULT" in calls_text
    assert "LIEN" in calls_text


def test_parse_recorder_output_extracts_canonical_record(monkeypatch):
    monkeypatch.setenv("RECORDER_DIRECT_ENABLED", "true")
    responses = [LANDMARK_NOTS_WITH_PARCEL, "", ""]
    with patch("realtorfarm.collectors.recorder_direct.run_task", side_effect=responses):
        records, candidates = collect_recorder_direct(city="Burien", lookback_days=1)
    assert len(records) == 1
    assert records[0]["owner"] == "BURIEN SAMPLE OWNER LLC"
    assert records[0]["property_address"] == "12345 6th Ave SW, Burien, WA 98146"
    assert records[0]["parcel_id"] == "123450-0678"
    assert records[0]["signal"] == "NOTS"
    assert records[0]["case_id"] == "20260522000456"
    assert records[0]["recorded_date"] == "2026-05-22"


def test_collect_recorder_direct_skips_failed_task_and_continues(monkeypatch):
    monkeypatch.setenv("RECORDER_DIRECT_ENABLED", "true")
    responses = [RuntimeError("Browser Use failed"), LANDMARK_NOTS_WITH_PARCEL, ""]
    with patch("realtorfarm.collectors.recorder_direct.run_task", side_effect=responses):
        records, candidates = collect_recorder_direct(city="Burien", lookback_days=1)
    assert isinstance(records, list)
    assert isinstance(candidates, list)


def test_collect_recorder_direct_returns_candidates_for_missing_parcel(monkeypatch):
    monkeypatch.setenv("RECORDER_DIRECT_ENABLED", "true")
    responses = [LANDMARK_NOD_MISSING_PARCEL, "", ""]
    with patch("realtorfarm.collectors.recorder_direct.run_task", side_effect=responses):
        records, candidates = collect_recorder_direct(city="Burien", lookback_days=1)
    assert records == []
    assert len(candidates) == 1
    assert candidates[0]["rejection_reason"] == "missing_parcel_id"
    assert candidates[0]["property_address"] == "999 SW 152nd St, Burien, WA 98166"


def test_collect_recorder_direct_handles_missing_api_key(monkeypatch):
    monkeypatch.setenv("RECORDER_DIRECT_ENABLED", "true")
    with patch("realtorfarm.collectors.recorder_direct.run_task", side_effect=ValueError("BROWSER_USE_API_KEY is required")):
        records, candidates = collect_recorder_direct(city="Burien", lookback_days=1)
    # ValueError must not propagate — collector must return empty lists
    assert records == []
    assert candidates == []
