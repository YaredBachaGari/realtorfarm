from __future__ import annotations
"""Use Browser Use Cloud to fill missing parcel_id or property_address for rejected candidates."""


def enrich_candidates(
    candidates: list[dict],
    *,
    city: str,
    max_enrichments: int = 10,
) -> list[dict[str, str]]:
    """Return canonical records built from enriched candidates (address or parcel filled)."""
    raise NotImplementedError
