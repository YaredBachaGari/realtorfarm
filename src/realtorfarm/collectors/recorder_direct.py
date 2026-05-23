"""Collect NOTS/NOD/Lien from King County Recorder Landmark via Browser Use Cloud."""
from __future__ import annotations

import os
import re
from datetime import date, timedelta

from .browser_use import run_task

LANDMARK_URL = "https://recordsearch.kingcounty.gov/LandmarkWeb/"

_DOC_TYPES = [
    ("NOTICE OF TRUSTEE SALE", "NOTS"),
    ("NOTICE OF DEFAULT", "NOD"),
    ("LIEN", "Lien"),
]

_PARCEL_RE = re.compile(r"\b([0-9]{6}-[0-9]{4}(?:-[0-9]{2})?)\b")
_RECORDING_NUMBER_RE = re.compile(r"\b(\d{14})\b")
_ADDRESS_RE = re.compile(
    r"(\d{1,6}\s+[^\n.;]{2,80}?\b(?:Ave|St|Rd|Dr|Ln|Ct|Pl|Way|Blvd)\b[^\n]{0,60}WA\s+\d{5})",
    re.I,
)


def collect_recorder_direct(
    *, city: str, lookback_days: int = 1
) -> tuple[list[dict[str, str]], list[dict]]:
    """Return canonical records and candidates from King County Recorder Landmark."""
    if os.environ.get("RECORDER_DIRECT_ENABLED", "").lower() != "true":
        return [], []

    end_date = date.today()
    start_date = end_date - timedelta(days=lookback_days)
    records: list[dict[str, str]] = []
    candidates: list[dict] = []

    for doc_type, signal in _DOC_TYPES:
        try:
            r, c = _collect_doc_type(
                doc_type=doc_type, signal=signal,
                city=city, start_date=start_date, end_date=end_date,
            )
            records.extend(r)
            candidates.extend(c)
        except Exception as exc:
            print(f"[recorder_direct] {doc_type} task failed for {city}: {exc}")

    return records, candidates


def _collect_doc_type(
    *, doc_type: str, signal: str, city: str, start_date: date, end_date: date,
) -> tuple[list[dict[str, str]], list[dict]]:
    task = (
        f'Go to {LANDMARK_URL} and search for documents of type "{doc_type}" '
        f"recorded between {start_date.isoformat()} and {end_date.isoformat()}. "
        f"For each result where the property address is in {city}, WA, return: "
        f"recording date, recording number, grantor name, property address, document type. "
        f"Return as plain text, one record per line."
    )
    result_text = run_task(task)
    if not result_text.strip():
        print(f"[recorder_direct] no {doc_type} results for {city}")
        return [], []
    return _parse_result(result_text, signal=signal, city=city, doc_type=doc_type)


def _parse_result(
    text: str, *, signal: str, city: str, doc_type: str,
) -> tuple[list[dict[str, str]], list[dict]]:
    """Parse the entire result text block as one record (not line-by-line).

    Browser Use returns multi-line blocks per result. We extract all fields
    from the full text block rather than scanning individual lines, so that
    fields spread across multiple lines (address, parcel, recording number,
    grantor) are all found together.
    """
    records: list[dict[str, str]] = []
    candidates: list[dict] = []

    # Split into record blocks separated by blank lines, then handle
    # single-record responses (no blank-line separator) as one block.
    blocks = re.split(r"\n\s*\n", text.strip())
    if not blocks:
        return [], []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        parcel_id = _extract_parcel(block)
        address = _extract_address(block, city=city)
        recording_number = _extract_recording_number(block)
        owner = _extract_owner(block)
        recorded_date = _extract_date(block)

        source_url = (
            f"browser-use://landmark/{recording_number}" if recording_number else LANDMARK_URL
        )

        if parcel_id and address:
            records.append({
                "owner": owner,
                "property_address": address,
                "parcel_id": parcel_id,
                "signal": signal,
                "source": "King County Recorder Landmark",
                "source_url": source_url,
                "recorded_date": recorded_date,
                "case_id": recording_number,
                "notes": f"Recorded document type: {doc_type}",
            })
        elif address or recording_number:
            candidates.append({
                "property_address": address,
                "parcel_id": parcel_id,
                "case_id": recording_number,
                "signals": [signal],
                "rejection_reason": (
                    "missing_parcel_id" if address and not parcel_id
                    else "missing_target_city_property_address"
                ),
                "source_url": source_url,
                "recorded_date": recorded_date,
            })

    return records, candidates


def _extract_parcel(text: str) -> str:
    m = _PARCEL_RE.search(text)
    return m.group(1) if m else ""


def _extract_recording_number(text: str) -> str:
    m = _RECORDING_NUMBER_RE.search(text)
    return m.group(1) if m else ""


def _extract_address(text: str, *, city: str) -> str:
    city_re = re.compile(
        rf"(\d{{1,6}}\s+[^\n.;]{{2,80}}?\b{re.escape(city)}\b[^\n]{{0,30}}WA\s+\d{{5}}(?:-\d{{4}})?)",
        re.I,
    )
    m = city_re.search(text)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    m = _ADDRESS_RE.search(text)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _extract_owner(text: str) -> str:
    m = re.search(r"(?:Grantor|Owner)\s*[:\-]?\s*([^\n,]{2,80})", text, re.I)
    return m.group(1).strip().upper() if m else "UNKNOWN OWNER"


def _extract_date(text: str) -> str:
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", text)
    if m:
        try:
            from datetime import datetime
            return datetime.strptime(m.group(1), "%m/%d/%Y").date().isoformat()
        except ValueError:
            pass
    return date.today().isoformat()
