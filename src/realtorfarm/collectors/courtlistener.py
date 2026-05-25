"""CourtListener REST API wrapper — searches federal court dockets and party records.

Uses API v4: https://www.courtlistener.com/api/rest/v4
Chapter filtering uses the /bankruptcy-information/ endpoint; v3 /dockets/ does not
support a `chapter` filter parameter.
"""
from __future__ import annotations

import os
import time

import requests

COURTLISTENER_BASE = "https://www.courtlistener.com/api/rest/v4"
MAX_PAGES = 200  # safeguard: 200 × 100 = 20,000 dockets; covers any realistic lookback window
_RATE_SLEEP = 0.35  # stay under 3 req/sec free-tier limit between per-docket detail fetches


def search_dockets(
    *,
    court: str,
    chapter: int,
    date_filed_gte: str,
    date_filed_lte: str,
    api_key: str | None = None,
    page_size: int = 100,
) -> list[dict]:
    """Return all dockets matching court/chapter/date range.

    Uses /bankruptcy-information/ (v4) to filter by chapter, then fetches each
    docket's details (docket_number, case_name, date_filed) individually.
    Returns a flat list of dicts with keys: id, docket_number, case_name, date_filed.
    """
    key = api_key or os.environ.get("COURTLISTENER_API_KEY", "")
    if not key:
        raise ValueError("COURTLISTENER_API_KEY is required")

    headers = {"Authorization": f"Token {key}"}

    # Step 1: collect all bankruptcy-information records matching court/chapter/date
    params: dict = {
        "docket__court": court,
        "chapter": str(chapter),
        "docket__date_filed__gte": date_filed_gte,
        "docket__date_filed__lte": date_filed_lte,
        "page_size": page_size,
    }
    bk_items: list[dict] = []
    url: str | None = f"{COURTLISTENER_BASE}/bankruptcy-information/"
    page = 0
    while url and page < MAX_PAGES:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        bk_items.extend(data.get("results", []))
        url = data.get("next")
        params = {}  # next URL already encodes all query params
        page += 1

    # Step 2: fetch docket details for each bankruptcy case
    results: list[dict] = []
    for item in bk_items:
        docket_url = item.get("docket", "")
        if not docket_url:
            continue
        # Extract numeric ID from URL like ".../dockets/73387773/"
        docket_id_str = docket_url.rstrip("/").split("/")[-1]
        if not docket_id_str.isdigit():
            continue
        docket_id = int(docket_id_str)
        try:
            time.sleep(_RATE_SLEEP)
            dr = requests.get(docket_url, headers=headers, timeout=30)
            dr.raise_for_status()
            d = dr.json()
            results.append({
                "id": docket_id,
                "docket_number": d.get("docket_number", ""),
                "case_name": d.get("case_name", ""),
                "date_filed": d.get("date_filed", date_filed_lte),
            })
        except requests.RequestException:
            # Skip individual dockets we can't fetch rather than failing the whole chapter
            continue

    return results


def get_parties(
    *,
    docket_id: int,
    api_key: str | None = None,
) -> list[dict]:
    """Return party records for a docket.

    Each dict has keys: name, contact_information, party_types.
    contact_information is a list of address dicts (address1, city, state, zip_code).
    party_types is a list of role dicts (name: "Debtor" | "Joint Debtor" | ...).
    """
    key = api_key or os.environ.get("COURTLISTENER_API_KEY", "")
    if not key:
        raise ValueError("COURTLISTENER_API_KEY is required")

    headers = {"Authorization": f"Token {key}"}
    url: str | None = f"{COURTLISTENER_BASE}/parties/"
    params: dict = {
        "docket": docket_id,
        "fields": "name,contact_information,party_types",
    }
    parties: list[dict] = []
    page = 0
    while url and page < MAX_PAGES:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        parties.extend(data.get("results", []))
        url = data.get("next")
        params = {}
        page += 1
    return parties
