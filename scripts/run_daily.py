#!/usr/bin/env python3
"""Daily runner: validate records, score leads, write data= output, optionally upload it."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from realtorfarm.blob import upload_file_to_vercel_blob
from realtorfarm.reporting import build_source_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default="burien", help="City slug used for organized data/output paths and blob prefix")
    parser.add_argument("--input", help="CSV/JSON records collected from source adapters; defaults to data/cities/<city>/daily/merged.csv")
    parser.add_argument("--output", help="Output file; defaults to out/<city>/distressed-latest.json.txt")
    parser.add_argument("--max-records", default="99", help="Cap daily test extraction below 100 records")
    parser.add_argument("--lookback-days", help="Do not process records older than this many days; defaults to 30 in active mode, 0 in delta mode, otherwise 10")
    parser.add_argument("--mode", choices=["active", "delta"], help="active = rolling 30-day lead feed; delta = same-day-only report")
    parser.add_argument("--accessed-date", help="Override accessed date as YYYY-MM-DD for reproducible tests")
    parser.add_argument("--upload-blob", action="store_true", help="Upload the generated data= output to Vercel Blob")
    parser.add_argument("--blob-prefix", help="Vercel Blob folder/prefix for daily outputs; defaults to city slug")
    parser.add_argument("--blob-latest-name", default="latest.json.txt", help="Stable Vercel Blob filename overwritten each run")
    parser.add_argument("--source-report", help="Source health report JSON; defaults to out/<city>/source-report-latest.json")
    args = parser.parse_args()
    city = args.city.strip().lower().replace(" ", "-")
    input_path = args.input or f"data/cities/{city}/daily/merged.csv"
    output_path = args.output or f"out/{city}/distressed-latest.json.txt"
    source_report_path = args.source_report or f"out/{city}/source-report-latest.json"
    blob_prefix = args.blob_prefix or city
    lookback_days = args.lookback_days
    if lookback_days is None:
        lookback_days = "30" if args.mode == "active" else "0" if args.mode == "delta" else "10"

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    common = [
        "--input", input_path,
        "--max-records", args.max_records,
        "--lookback-days", lookback_days,
    ]
    if args.accessed_date:
        common.extend(["--accessed-date", args.accessed_date])
    subprocess.check_call([sys.executable, "-m", "realtorfarm.cli", "validate", *common])
    subprocess.check_call([
        sys.executable, "-m", "realtorfarm.cli", "hunt", *common, "--evidence", "--output", output_path,
    ])
    report = build_source_report(
        city=city,
        input_path=input_path,
        accessed_date=args.accessed_date or date.today(),
        lookback_days=int(lookback_days),
        max_records=int(args.max_records),
    )
    Path(source_report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(source_report_path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output_path}")
    print(f"wrote source report {source_report_path}")
    if args.upload_blob:
        accessed = date.fromisoformat(args.accessed_date) if args.accessed_date else date.today()
        dated_pathname = f"{blob_prefix.rstrip('/')}/{accessed.isoformat()}.json.txt"
        latest_pathname = f"{blob_prefix.rstrip('/')}/{args.blob_latest_name.lstrip('/')}"
        dated = upload_file_to_vercel_blob(output_path, pathname=dated_pathname)
        latest = upload_file_to_vercel_blob(output_path, pathname=latest_pathname)
        print(f"uploaded Vercel Blob dated={dated.get('pathname', dated_pathname)} latest={latest.get('pathname', latest_pathname)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
