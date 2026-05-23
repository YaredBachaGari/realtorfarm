from __future__ import annotations
"""Phase B stub: Washington Courts name/case search (probate, eviction, civil judgment).

When implemented, this collector will use Browser Use Cloud to query
https://www.courts.wa.gov/index.cfm?fa=home.contentDisplay&location=nameAndCaseSearch
for the target city, extract probate/eviction case records, and return canonical rows.

Register in collectors/__init__.py collect_for_city() when ready.
"""


def collect_courts(*, city: str, lookback_days: int = 1) -> tuple[list[dict], list[dict]]:
    """Phase B — not yet implemented."""
    return [], []
