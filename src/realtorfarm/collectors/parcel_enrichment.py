"""Use Browser Use Cloud to fill missing parcel_id or property_address for rejected candidates."""
from __future__ import annotations

import re
from datetime import date

from .browser_use import run_task

PARCEL_VIEWER_URL = "https://parcelviewer.kingcounty.gov"

_PARCEL_RE = re.compile(r"\b([0-9]{6}-[0-9]{4}(?:-[0-9]{2})?)\b")
_ADDRESS_RE = re.compile(
    r"(\d{1,6}\s+[^\n.;]{2,80}?\b(?:Ave|St|Rd|Dr|Ln|Ct|Pl|Way|Blvd)\b[^\n]{0,60}WA\s+\d{5})",
    re.I,
)

_ENRICHABLE = {"missing_parcel_id", "missing_target_city_property_address"}


def enrich_candidates(
    candidates: list[dict],
    *,
    city: str,
    max_enrichments: int = 10,
) -> list[dict[str, str]]:
    """Return canonical records built from Browser Use parcel enrichment of rejected candidates."""
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
            print(f"[parcel_enrichment] Browser Use failed for {candidate.get('case_id', '?')}: {exc}")
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
        task = (
            f"Go to {PARCEL_VIEWER_URL} and search for parcel number {parcel_id}. "
            f"Return the situs address, parcel account number, and owner name as plain text."
        )
    elif address and not parcel_id:
        task = (
            f"Go to {PARCEL_VIEWER_URL} and search for this address: {address}. "
            f"Return the parcel account number, situs address, and owner name as plain text."
        )
    else:
        return None

    result_text = run_task(task)
    if not result_text:
        return None

    filled_parcel = parcel_id or _extract_parcel(result_text)
    filled_address = address or _extract_address(result_text, city=city)

    if not filled_parcel or not filled_address:
        return None

    signals = candidate.get("signals", [])
    if not signals:
        print(f"[parcel_enrichment] candidate {candidate.get('case_id', '?')} has no signals after enrichment — skipping")
        return None

    return {
        "owner": _extract_owner(result_text),
        "property_address": filled_address,
        "parcel_id": filled_parcel,
        "signal": signals[0],
        "source": "public legal notice + parcel viewer enrichment",
        "source_url": candidate.get("source_url", ""),
        "recorded_date": candidate.get("recorded_date", date.today().isoformat()),
        "case_id": candidate.get("case_id", ""),
        "notes": "Address or parcel enriched via King County Parcel Viewer (Browser Use Cloud)",
    }


def _extract_parcel(text: str) -> str:
    m = _PARCEL_RE.search(text)
    return m.group(1) if m else ""


def _extract_address(text: str, *, city: str) -> str:
    city_pattern = re.compile(
        rf"(\d{{1,6}}\s+[^\n.;]{{2,80}}?\b{re.escape(city)}\b[^\n]{{0,30}}WA\s+\d{{5}}(?:-\d{{4}})?)",
        re.I,
    )
    m = city_pattern.search(text)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    m = _ADDRESS_RE.search(text)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _extract_owner(text: str) -> str:
    m = re.search(r"(?:Owner|Taxpayer)\s*[:\-]?\s*([^\n]+)", text, re.I)
    return m.group(1).strip().upper() if m else "UNKNOWN OWNER"
