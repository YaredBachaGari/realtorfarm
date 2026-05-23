"""Collect Probate/Eviction signals from Washington Courts case search via Browser Use Cloud."""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta

from .browser_use import run_task

COURTS_URL = (
    "https://www.courts.wa.gov/index.cfm?fa=home.contentDisplay&location=nameAndCaseSearch"
)

_CASE_TYPES = [
    ("Probate/Guardianship/Trust", "Probate"),
    ("Unlawful Detainer", "Eviction"),
]

_PARCEL_RE = re.compile(r"\b([0-9]{6}-[0-9]{4}(?:-[0-9]{2})?)\b")
_CASE_NUMBER_RE = re.compile(r"\b(\d{2,4}-\d{1}-\d{5}-\d+(?:\s+[A-Z]{2,4})?)\b")
_ADDRESS_RE = re.compile(
    r"(\d{1,6}\s+[^\n.;]{2,80}?\b(?:Ave|St|Rd|Dr|Ln|Ct|Pl|Way|Blvd)\b[^\n]{0,60}WA\s+\d{5})",
    re.I,
)
_MIN_LOOKBACK = 7


def collect_courts(
    *, city: str, lookback_days: int = 1
) -> tuple[list[dict[str, str]], list[dict]]:
    """Return canonical records and candidates from Washington Courts case search."""
    if os.environ.get("COURTS_ENABLED", "").lower() != "true":
        return [], []

    effective_lookback = max(lookback_days, _MIN_LOOKBACK)
    end_date = date.today()
    start_date = end_date - timedelta(days=effective_lookback)
    records: list[dict[str, str]] = []
    candidates: list[dict] = []

    for case_type, signal in _CASE_TYPES:
        try:
            r, c = _collect_case_type(
                case_type=case_type, signal=signal,
                city=city, start_date=start_date, end_date=end_date,
            )
            records.extend(r)
            candidates.extend(c)
        except (RuntimeError, TimeoutError, OSError) as exc:
            print(f"[courts] {case_type} task failed for {city}: {exc}")

    return records, candidates


def _collect_case_type(
    *, case_type: str, signal: str, city: str, start_date: date, end_date: date,
) -> tuple[list[dict[str, str]], list[dict]]:
    task = (
        f"Go to {COURTS_URL} and search for {case_type} cases "
        f"filed in King County between {start_date.isoformat()} and {end_date.isoformat()}. "
        f"For each result where any party's address is in {city}, WA, return: "
        f"case number, filing date, case type, party names, and party addresses. "
        f"Return as plain text, one record per line."
    )
    result_text = run_task(task)
    if not result_text.strip():
        print(f"[courts] no {case_type} results for {city}")
        return [], []
    return _parse_result(result_text, signal=signal, city=city, case_type=case_type)


def _parse_result(
    text: str, *, signal: str, city: str, case_type: str,
) -> tuple[list[dict[str, str]], list[dict]]:
    records: list[dict[str, str]] = []
    candidates: list[dict] = []

    for block in re.split(r"\n\s*\n", text.strip()):
        block = block.strip()
        if not block:
            continue
        parcel_id = _extract_parcel(block)
        address = _extract_address(block, city=city)
        case_number = _extract_case_number(block)
        owner = _extract_owner(block)
        filing_date = _extract_date(block)

        if parcel_id and address:
            records.append({
                "owner": owner,
                "property_address": address,
                "parcel_id": parcel_id,
                "signal": signal,
                "source": "Washington Courts",
                "source_url": COURTS_URL,
                "recorded_date": filing_date,
                "case_id": case_number,
                "notes": f"Court case type: {case_type}",
            })
        elif address or case_number:
            candidates.append({
                "property_address": address,
                "parcel_id": parcel_id,
                "case_id": case_number,
                "signals": [signal],
                "rejection_reason": (
                    "missing_parcel_id" if address and not parcel_id
                    else "missing_target_city_property_address"
                ),
                "source_url": COURTS_URL,
                "recorded_date": filing_date,
            })

    return records, candidates


def _extract_parcel(text: str) -> str:
    m = _PARCEL_RE.search(text)
    return m.group(1) if m else ""


def _extract_case_number(text: str) -> str:
    m = _CASE_NUMBER_RE.search(text)
    return m.group(1).strip() if m else ""


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
    m = re.search(
        r"(?:Petitioner|Plaintiff|Grantor|Party)\s*[:\-]?\s*([^\n,]{2,80})", text, re.I
    )
    return m.group(1).strip().upper() if m else "UNKNOWN OWNER"


def _extract_date(text: str) -> str:
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", text)
    if m:
        try:
            return datetime.strptime(m.group(1), "%m/%d/%Y").date().isoformat()
        except ValueError:
            pass
    return date.today().isoformat()
