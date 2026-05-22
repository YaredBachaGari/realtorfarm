import csv
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from realtorfarm.extractors.public_notices import scrape_notice_sources_with_diagnostics
from realtorfarm.reporting import build_source_report

FIELDNAMES = ["owner", "property_address", "parcel_id", "signal", "source", "source_url", "recorded_date", "case_id", "notes"]


def write_records(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def test_source_report_explains_date_window_and_qualification_counts(tmp_path: Path):
    records = tmp_path / "merged.csv"
    write_records(records, [
        {
            "owner": "Older Owner",
            "property_address": "12215 Des Moines Memorial Drive S Unit B, Burien, WA 98168",
            "parcel_id": "8944030050",
            "signal": "NOTS",
            "source": "public legal notice",
            "source_url": "file:///older.txt",
            "recorded_date": "2026-05-11",
            "case_id": "20260511000326",
            "notes": "valid but outside same-day window",
        },
        {
            "owner": "Today Owner",
            "property_address": "12345 6th Ave SW, Burien, WA 98146",
            "parcel_id": "123450-0678",
            "signal": "NOTS",
            "source": "public legal notice",
            "source_url": "file:///today.txt",
            "recorded_date": "2026-05-22",
            "case_id": "20260522000123",
            "notes": "valid same-day record",
        },
        {
            "owner": "Undated Owner",
            "property_address": "9876 1st Ave S, Burien, WA 98148",
            "parcel_id": "987650-4321",
            "signal": "Probate",
            "source": "public legal notice",
            "source_url": "file:///undated.txt",
            "recorded_date": "",
            "case_id": "26-4-01234-1",
            "notes": "missing recorded date",
        },
    ])

    report = build_source_report(
        city="burien",
        input_path=records,
        accessed_date="2026-05-22",
        lookback_days=0,
        max_records=99,
    )

    assert report["city"] == "burien"
    assert report["pipeline_status"] == "active_records_found"
    assert report["input"]["raw_records"] == 3
    assert report["input"]["accepted_records"] == 1
    assert report["input"]["rejected_date_window"] == 1
    assert report["input"]["rejected_missing_or_invalid_date"] == 1
    assert report["output"]["properties"] == 1
    assert report["output"]["outreach_qualifying"] == 1
    assert report["sources"] == [
        {
            "name": "public legal notice",
            "raw_records": 3,
            "accepted_records": 1,
            "rejected_date_window": 1,
            "rejected_missing_or_invalid_date": 1,
            "properties": 1,
            "outreach_qualifying": 1,
        }
    ]


def test_source_report_labels_empty_collector_pipeline(tmp_path: Path):
    records = tmp_path / "merged.csv"
    write_records(records, [])

    report = build_source_report(
        city="kent",
        input_path=records,
        accessed_date="2026-05-22",
        lookback_days=30,
        max_records=99,
    )

    assert report["pipeline_status"] == "empty_collector_feed"
    assert report["recommended_next_action"] == "populate_and_verify_source collectors; do not interpret zero rows as zero market distress"


def test_notice_diagnostics_queue_candidates_missing_parcel(tmp_path: Path):
    notice = tmp_path / "missing-parcel.html"
    notice.write_text(
        """
        <h1>NOTICE OF TRUSTEE'S SALE TS No.: 2026-00123-WA</h1>
        <p>Grantor: JANE Q OWNER</p>
        <p>Property Address: 12345 6th Ave SW, Burien, WA 98146</p>
        <p>Recorded on May 20, 2026 as Instrument No. 20260520000123.</p>
        """,
        encoding="utf-8",
    )

    records, diagnostics = scrape_notice_sources_with_diagnostics(
        [str(notice)],
        accessed_date="2026-05-21",
        target_city="Burien",
    )

    assert records == []
    assert diagnostics["accepted_records"] == 0
    assert diagnostics["candidates"][0]["source_url"] == str(notice)
    assert diagnostics["candidates"][0]["rejection_reason"] == "missing_parcel_id"
    assert diagnostics["candidates"][0]["property_address"] == "12345 6th Ave SW, Burien, WA 98146"
    assert diagnostics["candidates"][0]["signals"] == ["NOTS"]


def test_cli_scrape_notices_writes_candidate_diagnostics(tmp_path: Path):
    notice = tmp_path / "missing-parcel.html"
    candidates = tmp_path / "candidates.json"
    notice.write_text(
        """
        <h1>NOTICE OF TRUSTEE'S SALE TS No.: 2026-00123-WA</h1>
        <p>Grantor: JANE Q OWNER</p>
        <p>Property Address: 12345 6th Ave SW, Burien, WA 98146</p>
        <p>Recorded on May 20, 2026 as Instrument No. 20260520000123.</p>
        """,
        encoding="utf-8",
    )

    subprocess.check_call([
        sys.executable,
        "-m",
        "realtorfarm.cli",
        "scrape-notices",
        "--source",
        str(notice),
        "--accessed-date",
        "2026-05-21",
        "--candidates-output",
        str(candidates),
    ])

    diagnostics = json.loads(candidates.read_text(encoding="utf-8"))
    assert diagnostics["accepted_records"] == 0
    assert diagnostics["candidates"][0]["rejection_reason"] == "missing_parcel_id"


def test_run_daily_active_mode_uses_30_day_lookback(tmp_path: Path):
    records = tmp_path / "merged.csv"
    output = tmp_path / "distressed-latest.json.txt"
    report = tmp_path / "source-report-latest.json"
    write_records(records, [
        {
            "owner": "Older Owner",
            "property_address": "12215 Des Moines Memorial Drive S Unit B, Burien, WA 98168",
            "parcel_id": "8944030050",
            "signal": "NOTS",
            "source": "public legal notice",
            "source_url": "file:///older.txt",
            "recorded_date": "2026-05-11",
            "case_id": "20260511000326",
            "notes": "valid active-window record",
        }
    ])

    subprocess.check_call([
        sys.executable,
        "scripts/run_daily.py",
        "--city",
        "burien",
        "--input",
        str(records),
        "--output",
        str(output),
        "--source-report",
        str(report),
        "--accessed-date",
        "2026-05-22",
        "--mode",
        "active",
    ])

    report_payload = json.loads(report.read_text(encoding="utf-8"))
    output_payload = json.loads(output.read_text(encoding="utf-8").removeprefix("data= "))
    assert report_payload["lookback_days"] == 30
    assert output_payload["properties"][0]["parcel id"] == "8944030050"


def test_run_daily_blob_upload_plan_preserves_historical_snapshots():
    from scripts.run_daily import build_blob_upload_plan

    plan = build_blob_upload_plan(
        blob_prefix="burien",
        accessed_date=date(2026, 5, 22),
        latest_name="latest.json.txt",
    )

    assert plan == [
        {"label": "dated", "pathname": "burien/2026-05-22.json.txt", "allow_overwrite": False},
        {"label": "latest", "pathname": "burien/latest.json.txt", "allow_overwrite": True},
    ]


def test_run_daily_writes_source_report_file(tmp_path: Path):
    records = tmp_path / "merged.csv"
    output = tmp_path / "distressed-latest.json.txt"
    report = tmp_path / "source-report-latest.json"
    write_records(records, [
        {
            "owner": "Today Owner",
            "property_address": "12345 6th Ave SW, Burien, WA 98146",
            "parcel_id": "123450-0678",
            "signal": "NOTS",
            "source": "public legal notice",
            "source_url": "file:///today.txt",
            "recorded_date": "2026-05-22",
            "case_id": "20260522000123",
            "notes": "valid same-day record",
        }
    ])

    subprocess.check_call([
        sys.executable,
        "scripts/run_daily.py",
        "--city",
        "burien",
        "--input",
        str(records),
        "--output",
        str(output),
        "--source-report",
        str(report),
        "--accessed-date",
        "2026-05-22",
        "--lookback-days",
        "0",
    ])

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["city"] == "burien"
    assert payload["input"]["raw_records"] == 1
    assert payload["output"]["outreach_qualifying"] == 1
