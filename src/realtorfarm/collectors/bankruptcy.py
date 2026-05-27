"""Collect Bankruptcy signals from CourtListener (U.S. Bankruptcy Court, Western District WA)."""
from __future__ import annotations

import os
import re
import time
from datetime import date, timedelta

import requests

from .courtlistener import get_parties, search_dockets

_COURT = "wawb"  # Western District of Washington bankruptcy court
_CHAPTERS = [7, 11, 13]
_MIN_LOOKBACK = 7  # CourtListener indexing lag up to 48h; 7 days ensures full coverage
_RATE_SLEEP = 0.35  # stay under 3 req/sec CourtListener free-tier limit
_CHAPTER_SLEEP = 13  # seconds between chapter queries — keeps us under 5 req/min free-tier limit

_COURTLISTENER_DOCKET_BASE = "https://www.courtlistener.com"  # human-readable docket URLs (not the API base)

# City → zip code mapping (same cities as other collectors)
_CITY_ZIPS: dict[str, list[str]] = {
    "burien":  ["98146", "98148", "98166", "98168"],
    "kent":    ["98030", "98031", "98032", "98042"],
    "tukwila": ["98168", "98188"],
}


def collect_bankruptcy(
    *, city: str, lookback_days: int = 1
) -> tuple[list[dict[str, str]], list[dict]]:
    """Return bankruptcy candidates for *city* from CourtListener WAWB dockets.

    All results are candidates (bankruptcy filings never include a parcel number).
    *lookback_days* is promoted to _MIN_LOOKBACK if smaller, to account for indexing lag.
    """
    if os.environ.get("BANKRUPTCY_ENABLED", "").lower() != "true":
        return [], []

    effective_lookback = max(lookback_days, _MIN_LOOKBACK)
    end_date = date.today()
    start_date = end_date - timedelta(days=effective_lookback)
    target_zips = set(_CITY_ZIPS.get(city.lower(), []))

    records: list[dict[str, str]] = []
    candidates: list[dict] = []

    for i, chapter in enumerate(_CHAPTERS):
        if i > 0:
            time.sleep(_CHAPTER_SLEEP)  # pace requests to stay under 5/min CourtListener limit
        try:
            _, c = _collect_chapter(
                chapter=chapter,
                city=city,
                target_zips=target_zips,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
            )
            candidates.extend(c)
        except requests.HTTPError as exc:
            print(f"[bankruptcy] Chapter {chapter} task failed for {city}: {exc}")
            # CourtListener rate-limited — skip remaining chapters; they'll fail identically.
            # The circuit breaker in courtlistener._get_with_retry will still block redundant
            # network calls even if we didn't break here.
            if exc.response is None or exc.response.status_code == 429:
                print(f"[bankruptcy] CourtListener rate-limited — skipping remaining chapters for {city}")
                break
        except (RuntimeError, TimeoutError, OSError, ValueError) as exc:
            print(f"[bankruptcy] Chapter {chapter} task failed for {city}: {exc}")

    candidates = _deduplicate(candidates)
    return records, candidates


# ── Chapter collector ─────────────────────────────────────────────────────────

def _collect_chapter(
    *,
    chapter: int,
    city: str,
    target_zips: set[str],
    start_date: str,
    end_date: str,
) -> tuple[list, list]:
    dockets = search_dockets(
        court=_COURT,
        chapter=chapter,
        date_filed_gte=start_date,
        date_filed_lte=end_date,
    )
    if not dockets:
        print(f"[bankruptcy] no Chapter {chapter} filings found in {_COURT}")
        return [], []

    candidates = []
    for docket in dockets:
        time.sleep(_RATE_SLEEP)
        candidate = _process_docket(
            docket=docket, chapter=chapter, target_zips=target_zips
        )
        if candidate is not None:
            candidates.append(candidate)

    if not candidates:
        print(f"[bankruptcy] no Chapter {chapter} filings matched {city}")

    return [], candidates


# ── Docket processor ──────────────────────────────────────────────────────────

def _process_docket(
    *, docket: dict, chapter: int, target_zips: set[str]
) -> dict | None:
    """Return a candidate dict for this docket, or None if outside target cities."""
    docket_id = docket["id"]
    docket_number = docket.get("docket_number", "")
    case_name = docket.get("case_name", "")
    date_filed = docket.get("date_filed", date.today().isoformat())
    source_url = f"{_COURTLISTENER_DOCKET_BASE}/docket/{docket_id}/"
    debtor_name = re.sub(r"(?i)^in\s+re\s+", "", case_name).strip()

    parties = get_parties(docket_id=docket_id)
    debtor = _find_debtor_party(parties)

    if debtor:
        address, zip_code = _extract_debtor_address(debtor)
        if zip_code and zip_code in target_zips:
            return {
                "property_address": address,
                "parcel_id":        "",
                "case_id":          docket_number,
                "signals":          ["Bankruptcy"],
                "rejection_reason": "missing_parcel_id",
                "source_url":       source_url,
                "recorded_date":    date_filed,
                "notes":            f"Chapter {chapter} bankruptcy; debtor: {debtor_name}",
            }
        elif zip_code:
            # Has an address but it's outside our target cities — skip
            return None

    # Either no debtor party record exists in CourtListener, or the debtor has no address data.
    # Distinguish the two cases in notes so human reviewers can triage efficiently.
    if debtor is None:
        address_note = "no debtor party found in CourtListener"
    else:
        address_note = "debtor party found but no address in CourtListener"

    return {
        "property_address": "",
        "parcel_id":        "",
        "case_id":          docket_number,
        "signals":          ["Bankruptcy"],
        "rejection_reason": "missing_debtor_address",
        "source_url":       source_url,
        "recorded_date":    date_filed,
        "notes":            f"Chapter {chapter} bankruptcy; debtor: {debtor_name}; {address_note}",
    }


# ── Party helpers ─────────────────────────────────────────────────────────────

def _find_debtor_party(parties: list[dict]) -> dict | None:
    """Return the first Debtor or Joint Debtor party, or None."""
    debtor_roles = {"Debtor", "Joint Debtor"}
    for party in parties:
        for pt in party.get("party_types", []):
            if pt.get("name") in debtor_roles:
                return party
    return None


def _extract_debtor_address(party: dict) -> tuple[str, str]:
    """Return (formatted_address, zip_code) from a CourtListener party dict."""
    contacts = party.get("contact_information", [])
    if not contacts:
        return "", ""

    contact = contacts[0]
    address1 = contact.get("address1", "").strip()
    city_val  = contact.get("city", "").strip()
    state     = contact.get("state", "").strip()
    zip_code  = contact.get("zip_code", "").strip()[:5]  # first 5 digits (ignore ZIP+4)

    if not zip_code:
        return "", ""
    if not (address1 and city_val):
        return "", zip_code

    address = f"{address1}, {city_val}, {state} {zip_code}".strip()
    return address, zip_code


# ── Deduplication ─────────────────────────────────────────────────────────────

def _deduplicate(candidates: list[dict]) -> list[dict]:
    """Remove duplicate candidates by case_id. Keeps first occurrence."""
    seen: set[str] = set()
    deduped: list[dict] = []
    for c in candidates:
        key = c.get("case_id", "")
        if key and key not in seen:
            seen.add(key)
            deduped.append(c)
        elif not key:
            print(f"[bankruptcy] candidate with empty case_id kept without deduplication: {c.get('notes', '')}")
            deduped.append(c)
    return deduped
