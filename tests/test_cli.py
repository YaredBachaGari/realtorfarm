import csv
import json
import subprocess
import sys
from pathlib import Path


def test_cli_outputs_requested_data_shape(tmp_path: Path):
    out = subprocess.check_output([
        sys.executable, "-m", "realtorfarm.cli", "hunt",
        "--input", "data/sample_records.csv",
        "--accessed-date", "2026-05-20",
    ], text=True)
    assert out.startswith("data= ")
    payload = json.loads(out.removeprefix("data= "))
    assert payload["accessed_date"] == "05/20/2026"
    assert len(payload["properties"]) == 2
    first = payload["properties"][0]
    assert first["Owner"] == "SYNTHETIC TEST OWNER A"
    assert first["parcel id"] == "TEST-PARCEL-0001"
    assert first["Signals"]["Tier_1"] == ["NOTS", "Probate"]


def test_hunt_defaults_to_recent_less_than_100_record_test_window(tmp_path: Path):
    input_path = tmp_path / "records.csv"
    fieldnames = ["owner", "property_address", "parcel_id", "signal", "source", "source_url", "recorded_date", "case_id", "notes"]
    rows = [{
        "owner": "Old Owner",
        "property_address": "999 Old Ave, Burien, WA, 98166",
        "parcel_id": "OLD-001",
        "signal": "NOTS",
        "source": "synthetic fixture",
        "source_url": "https://example.invalid/old/1",
        "recorded_date": "2026-05-09",
        "case_id": "OLD-001",
        "notes": "older than 10-day lookback",
    }]
    for index in range(105):
        rows.append({
            "owner": f"Recent Owner {index:03d}",
            "property_address": f"{index} Recent Ave, Burien, WA, 98166",
            "parcel_id": f"RECENT-{index:03d}",
            "signal": "NOTS",
            "source": "synthetic fixture",
            "source_url": f"https://example.invalid/recent/{index}",
            "recorded_date": "2026-05-20",
            "case_id": f"RECENT-{index:03d}",
            "notes": "recent synthetic record",
        })
    with input_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    out = subprocess.check_output([
        sys.executable, "-m", "realtorfarm.cli", "hunt",
        "--input", str(input_path),
        "--accessed-date", "2026-05-20",
    ], text=True)

    payload = json.loads(out.removeprefix("data= "))
    assert len(payload["properties"]) == 99
    assert all(item["parcel id"] != "OLD-001" for item in payload["properties"])
