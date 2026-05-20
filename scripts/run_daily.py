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
    args = parser.parse_args()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call([sys.executable, "-m", "realtorfarm.cli", "validate", "--input", args.input])
    subprocess.check_call([sys.executable, "-m", "realtorfarm.cli", "hunt", "--input", args.input, "--evidence", "--output", args.output])
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
