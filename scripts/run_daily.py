#!/usr/bin/env python3
"""Token-free daily runner: validate records, score leads, write data= output."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="CSV/JSON records collected from source adapters")
    parser.add_argument("--output", default="out/burien-distressed-latest.json.txt")
    parser.add_argument("--max-records", default="99", help="Cap daily test extraction below 100 records")
    parser.add_argument("--lookback-days", default="10", help="Do not process records older than this many days")
    parser.add_argument("--accessed-date", help="Override accessed date as YYYY-MM-DD for reproducible tests")
    args = parser.parse_args()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    common = [
        "--input", args.input,
        "--max-records", args.max_records,
        "--lookback-days", args.lookback_days,
    ]
    if args.accessed_date:
        common.extend(["--accessed-date", args.accessed_date])
    subprocess.check_call([sys.executable, "-m", "realtorfarm.cli", "validate", *common])
    subprocess.check_call([
        sys.executable, "-m", "realtorfarm.cli", "hunt", *common, "--evidence", "--output", args.output,
    ])
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
