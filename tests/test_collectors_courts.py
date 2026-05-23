import os
from unittest.mock import patch
from realtorfarm.collectors.courts import collect_courts


COURTS_PROBATE_OUTPUT = """
Case Number: 26-4-01234-1 KNT
Filing Date: 2026-05-20
Case Type: Probate/Guardianship/Trust
Petitioner: JOHN EXECUTOR
Party Address: 9876 1st Ave S, Burien, WA 98148
"""

COURTS_EVICTION_OUTPUT = """
Case Number: 26-2-05678-1 KNT
Filing Date: 2026-05-19
Case Type: Unlawful Detainer
Plaintiff: LANDLORD CORP LLC
Party Address: 13579 4th Ave SW, Burien, WA 98146
"""


def test_collect_courts_returns_empty_when_disabled():
    records, candidates = collect_courts(city="Burien", lookback_days=1)
    assert records == []
    assert candidates == []


def test_collect_courts_runs_one_task_per_case_type(monkeypatch):
    monkeypatch.setenv("COURTS_ENABLED", "true")
    with patch("realtorfarm.collectors.courts.run_task", return_value="") as mock_run:
        collect_courts(city="Burien", lookback_days=1)
    assert mock_run.call_count == 2
    calls_text = " ".join(str(c) for c in mock_run.call_args_list)
    assert "Probate" in calls_text
    assert "Unlawful Detainer" in calls_text


def test_parse_courts_output_extracts_canonical_record(monkeypatch):
    monkeypatch.setenv("COURTS_ENABLED", "true")
    responses = [COURTS_PROBATE_OUTPUT, ""]
    with patch("realtorfarm.collectors.courts.run_task", side_effect=responses):
        records, candidates = collect_courts(city="Burien", lookback_days=1)
    # No parcel in fixture → candidate, not record
    assert len(candidates) == 1
    assert candidates[0]["signals"] == ["Probate"]
    assert candidates[0]["case_id"] == "26-4-01234-1 KNT"
    assert candidates[0]["property_address"] == "9876 1st Ave S, Burien, WA 98148"
    assert candidates[0]["rejection_reason"] == "missing_parcel_id"


def test_collect_courts_skips_failed_task_and_continues(monkeypatch):
    monkeypatch.setenv("COURTS_ENABLED", "true")
    responses = [RuntimeError("Browser Use failed"), COURTS_EVICTION_OUTPUT]
    with patch("realtorfarm.collectors.courts.run_task", side_effect=responses):
        records, candidates = collect_courts(city="Burien", lookback_days=1)
    assert isinstance(records, list)
    assert isinstance(candidates, list)
    total = len(records) + len(candidates)
    assert total >= 1


def test_collect_courts_uses_minimum_7_day_lookback(monkeypatch):
    monkeypatch.setenv("COURTS_ENABLED", "true")
    with patch("realtorfarm.collectors.courts.run_task", return_value="") as mock_run:
        collect_courts(city="Burien", lookback_days=1)
    first_call_arg = mock_run.call_args_list[0][0][0]
    from datetime import date, timedelta
    seven_days_ago = (date.today() - timedelta(days=7)).isoformat()
    assert seven_days_ago in first_call_arg


def test_collect_courts_handles_missing_api_key(monkeypatch):
    monkeypatch.setenv("COURTS_ENABLED", "true")
    with patch("realtorfarm.collectors.courts.run_task", side_effect=ValueError("BROWSER_USE_API_KEY is required")):
        records, candidates = collect_courts(city="Burien", lookback_days=1)
    assert records == []
    assert candidates == []
