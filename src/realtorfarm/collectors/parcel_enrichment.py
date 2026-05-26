"""Enrich candidates by looking up missing parcel_id or address via King County GIS API.

Replaces the previous Browser Use Cloud implementation — the KC GIS REST API is
free, requires no authentication, and has no daily quota.
"""
from __future__ import annotations

from datetime import date

from .kc_gis import format_address, lookup_by_address, lookup_by_pin, pin_to_formatted

_ENRICHABLE = {"missing_parcel_id", "missing_target_city_property_address"}


def enrich_candidates(
    candidates: list[dict],
    *,
    city: str,
    max_enrichments: int = 10,
) -> list[dict[str, str]]:
    """Return canonical records built from KC GIS parcel enrichment of rejected candidates."""
    if max_enrichments == 0:
        return []

    records: list[dict[str, str]] = []
    count = 0

    for candidate in candidates:
        if count >= max_enrichments:
            break
        if candidate.get("rejection_reason") not in _ENRICHABLE:
            continue
        try:
            enriched = _enrich_one(candidate, city=city)
        except Exception as exc:
            print(f"[parcel_enrichment] KC GIS lookup failed for "
                  f"{candidate.get('case_id', '?')}: {exc}")
            count += 1
            continue
        if enriched:
            records.append(enriched)
        count += 1

    return records


def _enrich_one(candidate: dict, *, city: str) -> dict[str, str] | None:
    parcel_id = candidate.get("parcel_id", "")
    address = candidate.get("property_address", "")

    if parcel_id and not address:
        attrs = lookup_by_pin(parcel_id)
        if not attrs:
            return None
        filled_address = format_address(attrs)
        filled_parcel = pin_to_formatted(attrs["PIN"])
    elif address and not parcel_id:
        attrs = lookup_by_address(address)
        if not attrs:
            return None
        filled_address = format_address(attrs) or address
        filled_parcel = pin_to_formatted(attrs["PIN"])
    else:
        return None

    if not filled_parcel or not filled_address:
        return None

    signals = candidate.get("signals", [])
    return {
        "owner":            "UNKNOWN OWNER",
        "property_address": filled_address,
        "parcel_id":        filled_parcel,
        "signal":           signals[0] if signals else "",
        "source":           candidate.get("source_url", ""),
        "source_url":       candidate.get("source_url", ""),
        "recorded_date":    candidate.get("recorded_date", date.today().isoformat()),
        "case_id":          candidate.get("case_id", ""),
        "notes":            candidate.get("notes", ""),
        "listed_status":    "",
        "listing_date":     "",
        "listing_url":      "",
        "listing_source":   "",
    }
