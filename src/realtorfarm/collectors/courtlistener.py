"""CourtListener REST API wrapper — searches federal court dockets and party records."""
from __future__ import annotations

import os

import requests

COURTLISTENER_BASE = "https://www.courtlistener.com/api/rest/v3"


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

    Follows CourtListener pagination via ``next`` links automatically.
    Returns a flat list of docket dicts with keys: id, docket_number, case_name, date_filed.
    """
    key = api_key or os.environ.get("COURTLISTENER_API_KEY", "")
    if not key:
        raise ValueError("COURTLISTENER_API_KEY is required")

    headers = {"Authorization": f"Token {key}"}
    params: dict = {
        "court": court,
        "chapter": chapter,
        "date_filed__gte": date_filed_gte,
        "date_filed__lte": date_filed_lte,
        "fields": "id,docket_number,case_name,date_filed",
        "page_size": page_size,
    }

    results: list[dict] = []
    url: str | None = f"{COURTLISTENER_BASE}/dockets/"
    while url:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("results", []))
        url = data.get("next")
        params = {}  # next URL already encodes all query params

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
    params = {
        "docket": docket_id,
        "fields": "name,contact_information,party_types",
    }

    resp = requests.get(
        f"{COURTLISTENER_BASE}/parties/",
        headers=headers,
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])
