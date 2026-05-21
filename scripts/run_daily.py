#!/usr/bin/env python3
"""Daily runner: validate records, score leads, write data= output, optionally upload it."""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

from realtorfarm.blob import upload_file_to_vercel_blob


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default="burien", help="City slug used for organized data/output paths and blob prefix")
    parser.add_argument("--input", help="CSV/JSON records collected from source adapters; defaults to data/cities/<city>/daily/merged.csv")
    parser.add_argument("--output", help="Output file; defaults to out/<city>/distressed-latest.json.txt")
    parser.add_argument("--max-records", default="99", help="Cap daily test extraction below 100 records")
    parser.add_argument("--lookback-days", default="10", help="Do not process records older than this many days")
    parser.add_argument("--accessed-date", help="Override accessed date as YYYY-MM-DD for reproducible tests")
    parser.add_argument("--upload-blob", action="store_true", help="Upload the generated data= output to Vercel Blob")
    parser.add_argument("--blob-prefix", help="Vercel Blob folder/prefix for daily outputs; defaults to city slug")
    parser.add_argument("--blob-latest-name", default="latest.json.txt", help="Stable Vercel Blob filename overwritten each run")
    args = parser.parse_args()
    city = args.city.strip().lower().replace(" ", "-")
    input_path = args.input or f"data/cities/{city}/daily/merged.csv"
    output_path = args.output or f"out/{city}/distressed-latest.json.txt"
    blob_prefix = args.blob_prefix or city

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    common = [
        "--input", input_path,
        "--max-records", args.max_records,
        "--lookback-days", args.lookback_days,
    ]
    if args.accessed_date:
        common.extend(["--accessed-date", args.accessed_date])
    subprocess.check_call([sys.executable, "-m", "realtorfarm.cli", "validate", *common])
    subprocess.check_call([
        sys.executable, "-m", "realtorfarm.cli", "hunt", *common, "--evidence", "--output", output_path,
    ])
    print(f"wrote {output_path}")
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
