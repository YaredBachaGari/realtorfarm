#!/usr/bin/env python3
"""Normalize vendor/manual CSV headers into RealtorFarm's canonical schema."""
from __future__ import annotations

import argparse
import csv

CANONICAL = ["owner", "property_address", "parcel_id", "signal", "source", "source_url", "recorded_date", "case_id", "notes"]
ALIASES = {
    "address": "property_address", "property address": "property_address", "parcel": "parcel_id",
    "parcel number": "parcel_id", "tax parcel": "parcel_id", "document type": "signal",
    "record type": "signal", "url": "source_url", "recording date": "recorded_date", "case number": "case_id",
}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("output")
    args = p.parse_args()
    with open(args.input, newline="", encoding="utf-8") as src, open(args.output, "w", newline="", encoding="utf-8") as dst:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dst, fieldnames=CANONICAL)
        writer.writeheader()
        for row in reader:
            lowered = {k.strip().lower(): (v or "").strip() for k, v in row.items()}
            normalized = {name: "" for name in CANONICAL}
            for key, value in lowered.items():
                target = ALIASES.get(key, key)
                if target in normalized:
                    normalized[target] = value
            writer.writerow(normalized)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
