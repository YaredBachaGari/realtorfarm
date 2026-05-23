from __future__ import annotations
"""Collect NOTS/NOD/Liens from public legal notice publications via Firecrawl."""


def collect_legal_notices(*, city: str, lookback_days: int = 1) -> tuple[list[dict], list[dict]]:
    """Return (accepted_records, rejected_candidates) for target city from legal notice pubs."""
    raise NotImplementedError
