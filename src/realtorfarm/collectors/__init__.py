from __future__ import annotations

from .legal_notices import collect_legal_notices
from .treasury import collect_treasury


def collect_for_city(
    city: str,
    lookback_days: int = 1,
) -> tuple[list[dict[str, str]], list[dict]]:
    """Run all Phase A+C collectors for a city and return (records, candidates)."""
    records: list[dict[str, str]] = []
    candidates: list[dict] = []

    notice_records, notice_candidates = collect_legal_notices(city=city, lookback_days=lookback_days)
    records.extend(notice_records)
    candidates.extend(notice_candidates)

    treasury_records = collect_treasury(city=city)
    records.extend(treasury_records)

    return records, candidates
