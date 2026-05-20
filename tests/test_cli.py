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
