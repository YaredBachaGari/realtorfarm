#!/usr/bin/env python3
"""Collect distressed-property records for a single city and append to merged.csv."""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from realtorfarm.collectors import collect_for_city
from realtorfarm.collectors.parcel_enrichment import enrich_candidates

CANONICAL_FIELDNAMES = [
    "owner", "property_address", "parcel_id", "signal", "source", "source_url",
    "recorded_date", "case_id", "notes", "listed_status", "listing_date",
    "listing_url", "listing_source",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect and append distressed-property records")
    parser.add_argument("--city", required=True, help="City slug: burien, kent, or tukwila")
    parser.add_argument("--lookback-days", type=int, default=1, help="Days of notices to fetch")
    args = parser.parse_args()

    city_slug = args.city.strip().lower().replace(" ", "-")
    city_display = city_slug.title()
    merged_path = Path(f"data/cities/{city_slug}/daily/merged.csv")

    run_collection(city=city_display, lookback_days=args.lookback_days, merged_path=merged_path)
    return 0


def run_collection(*, city: str, lookback_days: int, merged_path: Path) -> None:
    existing = _load_existing(merged_path)
    existing_keys = {_dedupe_key(r) for r in existing}

    print(f"[collect] {city}: {len(existing)} existing records, fetching lookback={lookback_days}d")

    new_records, candidates = collect_for_city(city=city, lookback_days=lookback_days)

    max_enrichments = int(os.environ.get("BROWSER_USE_MAX_ENRICHMENTS", "10"))
    enriched = enrich_candidates(candidates, city=city, max_enrichments=max_enrichments)
    new_records.extend(enriched)

    delta = [r for r in new_records if _dedupe_key(r) not in existing_keys]
    print(f"[collect] {city}: {len(new_records)} collected, {len(delta)} net-new after dedup")

    _write_merged(merged_path, existing + delta)
    print(f"[collect] {city}: wrote {merged_path} ({len(existing) + len(delta)} total rows)")


def _dedupe_key(row: dict) -> tuple:
    return (
        row.get("parcel_id", ""),
        row.get("signal", ""),
        row.get("case_id", ""),
        row.get("source_url", ""),
    )


def _load_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _write_merged(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CANONICAL_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
