import csv
import sys
from pathlib import Path
from unittest.mock import patch

# scripts/ is added to pytest pythonpath in pyproject.toml
from collect_daily import run_collection


KENT_RECORD = {
    "owner": "KENT TEST OWNER LLC",
    "property_address": "220 4th Ave S, Kent, WA 98032",
    "parcel_id": "232204-9001",
    "signal": "NOTS",
    "source": "public legal notice",
    "source_url": "https://example.com/notice",
    "recorded_date": "2026-05-20",
    "case_id": "KENT-2026-0099",
    "notes": "Extracted from public legal notice text",
}


def _write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = ["owner", "property_address", "parcel_id", "signal", "source",
                  "source_url", "recorded_date", "case_id", "notes"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_collect_daily_appends_new_records(tmp_path, monkeypatch):
    monkeypatch.setenv("BROWSER_USE_MAX_ENRICHMENTS", "0")
    merged = tmp_path / "data" / "cities" / "kent" / "daily" / "merged.csv"
    _write_csv(merged, [])

    with patch("collect_daily.collect_for_city", return_value=([KENT_RECORD], [])):
        run_collection(city="Kent", lookback_days=1, merged_path=merged)

    rows = list(csv.DictReader(merged.open(newline="", encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["parcel_id"] == "232204-9001"


def test_collect_daily_deduplicates_existing_records(tmp_path, monkeypatch):
    monkeypatch.setenv("BROWSER_USE_MAX_ENRICHMENTS", "0")
    merged = tmp_path / "data" / "cities" / "kent" / "daily" / "merged.csv"
    _write_csv(merged, [KENT_RECORD])

    with patch("collect_daily.collect_for_city", return_value=([KENT_RECORD], [])):
        run_collection(city="Kent", lookback_days=1, merged_path=merged)

    rows = list(csv.DictReader(merged.open(newline="", encoding="utf-8")))
    assert len(rows) == 1  # no duplicate added


def test_collect_daily_appends_only_delta(tmp_path, monkeypatch):
    monkeypatch.setenv("BROWSER_USE_MAX_ENRICHMENTS", "0")
    merged = tmp_path / "data" / "cities" / "kent" / "daily" / "merged.csv"
    _write_csv(merged, [KENT_RECORD])

    new_record = {**KENT_RECORD, "parcel_id": "232204-9999", "case_id": "KENT-2026-0200"}

    with patch("collect_daily.collect_for_city", return_value=([KENT_RECORD, new_record], [])):
        run_collection(city="Kent", lookback_days=1, merged_path=merged)

    rows = list(csv.DictReader(merged.open(newline="", encoding="utf-8")))
    assert len(rows) == 2
    assert {r["parcel_id"] for r in rows} == {"232204-9001", "232204-9999"}


def test_collect_daily_creates_merged_csv_if_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("BROWSER_USE_MAX_ENRICHMENTS", "0")
    merged = tmp_path / "data" / "cities" / "kent" / "daily" / "merged.csv"
    # Do NOT pre-create the file

    with patch("collect_daily.collect_for_city", return_value=([KENT_RECORD], [])):
        run_collection(city="Kent", lookback_days=1, merged_path=merged)

    assert merged.exists()
    rows = list(csv.DictReader(merged.open(newline="", encoding="utf-8")))
    assert len(rows) == 1


def test_collect_for_city_calls_recorder_direct_when_enabled(monkeypatch):
    monkeypatch.setenv("RECORDER_DIRECT_ENABLED", "true")
    monkeypatch.setenv("BROWSER_USE_MAX_ENRICHMENTS", "0")
    with patch("realtorfarm.collectors.recorder_direct.run_task", return_value="") as mock_run, \
         patch("realtorfarm.collectors.legal_notices.scrape_url", return_value=""), \
         patch("realtorfarm.collectors.treasury.scrape_url", return_value=""):
        from realtorfarm.collectors import collect_for_city
        records, candidates = collect_for_city(city="Kent", lookback_days=1)
    assert mock_run.called
    assert isinstance(records, list)


def test_collect_for_city_calls_courts_when_enabled(monkeypatch):
    monkeypatch.setenv("COURTS_ENABLED", "true")
    monkeypatch.setenv("BROWSER_USE_MAX_ENRICHMENTS", "0")
    with patch("realtorfarm.collectors.courts.run_task", return_value="") as mock_run, \
         patch("realtorfarm.collectors.legal_notices.scrape_url", return_value=""), \
         patch("realtorfarm.collectors.treasury.scrape_url", return_value=""):
        from realtorfarm.collectors import collect_for_city
        records, candidates = collect_for_city(city="Kent", lookback_days=1)
    assert mock_run.called
    assert isinstance(records, list)


def test_collect_for_city_calls_reo_when_enabled(monkeypatch):
    monkeypatch.setenv("REO_ENABLED", "true")
    monkeypatch.setenv("REO_BROWSER_USE_MAX_TASKS", "0")  # Firecrawl only
    monkeypatch.setenv("BROWSER_USE_MAX_ENRICHMENTS", "0")
    with patch("realtorfarm.collectors.reo.scrape_url", return_value="") as mock_scrape, \
         patch("realtorfarm.collectors.legal_notices.scrape_url", return_value=""), \
         patch("realtorfarm.collectors.treasury.scrape_url", return_value=""):
        from realtorfarm.collectors import collect_for_city
        records, candidates = collect_for_city(city="Burien", lookback_days=1)
    # 4 HUD zip calls for Burien
    assert mock_scrape.call_count == 4
    assert isinstance(records, list)
