from __future__ import annotations

import os

from .legal_notices import collect_legal_notices
from .treasury import collect_treasury
from .recorder_direct import collect_recorder_direct
from .courts import collect_courts


def collect_for_city(
    city: str,
    lookback_days: int = 1,
) -> tuple[list[dict[str, str]], list[dict]]:
    """Run all active collectors for a city and return (records, candidates)."""
    records: list[dict[str, str]] = []
    candidates: list[dict] = []

    notice_records, notice_candidates = collect_legal_notices(city=city, lookback_days=lookback_days)
    records.extend(notice_records)
    candidates.extend(notice_candidates)

    treasury_records = collect_treasury(city=city)
    records.extend(treasury_records)

    # Outer guard skips Browser Use quota when flag is off.
    # collect_recorder_direct also self-guards for callers outside collect_for_city.
    if os.environ.get("RECORDER_DIRECT_ENABLED", "").lower() == "true":
        rec_records, rec_candidates = collect_recorder_direct(city=city, lookback_days=lookback_days)
        records.extend(rec_records)
        candidates.extend(rec_candidates)

    # Same dual-guard pattern as recorder_direct above.
    if os.environ.get("COURTS_ENABLED", "").lower() == "true":
        court_records, court_candidates = collect_courts(city=city, lookback_days=lookback_days)
        records.extend(court_records)
        candidates.extend(court_candidates)

    return records, candidates
