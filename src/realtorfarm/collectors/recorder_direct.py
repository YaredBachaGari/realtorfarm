"""Collect NOTS from King County Recorder Landmark Web using SeleniumBase CDP + Playwright.

SeleniumBase launches an undetected Chrome instance; Playwright connects to it over CDP.
sb.solve_captcha() handles reCAPTCHA v2 automatically — no API key needed.

Required env vars:
  RECORDER_DIRECT_ENABLED=true   — must be explicitly enabled
"""
from __future__ import annotations

import os
import re
from datetime import date, timedelta

from playwright.sync_api import sync_playwright
from seleniumbase import sb_cdp

LANDMARK_SEARCH_URL = (
    "https://recordsearch.kingcounty.gov/LandmarkWeb/search/index"
    "?theme=.blue&section=searchCriteriaDocType&quickSearchSelection="
)
LANDMARK_DOCTYPE_ENDPOINT = (
    "https://recordsearch.kingcounty.gov/LandmarkWeb/Search/DocumentTypeSearch"
)
LANDMARK_DETAIL_BASE = "https://recordsearch.kingcounty.gov/LandmarkWeb/Document/Index/"

_DOC_TYPES: list[tuple[str, str]] = [
    ("172", "NOTS"),          # Notice of Trustee Sale
    ("134,136,137", "Lien"),  # Lien types
]

_CITY_VARIANTS: dict[str, set[str]] = {
    "burien":  {"burien"},
    "kent":    {"kent"},
    "tukwila": {"tukwila"},
}


def collect_recorder_direct(
    *, city: str, lookback_days: int = 1
) -> tuple[list[dict[str, str]], list[dict]]:
    """Return candidates from KC Landmark Recorder for *city*."""
    if os.environ.get("RECORDER_DIRECT_ENABLED", "").lower() != "true":
        return [], []

    end_date = date.today()
    start_date = end_date - timedelta(days=lookback_days)
    city_variants = _CITY_VARIANTS.get(city.lower(), {city.lower()})
    records: list[dict[str, str]] = []
    candidates: list[dict] = []

    for doctype_ids, signal in _DOC_TYPES:
        try:
            r, c = _search_doc_type(
                doctype_ids=doctype_ids,
                signal=signal,
                city_variants=city_variants,
                start_date=start_date,
                end_date=end_date,
            )
            records.extend(r)
            candidates.extend(c)
        except Exception as exc:
            print(f"[recorder_direct] {signal} search failed for {city}: {exc}")

    return records, candidates


def _search_doc_type(
    *,
    doctype_ids: str,
    signal: str,
    city_variants: set[str],
    start_date: date,
    end_date: date,
) -> tuple[list, list]:
    """Run one document-type search via SeleniumBase CDP + Playwright."""
    sb = sb_cdp.Chrome()
    try:
        endpoint_url = sb.get_endpoint_url()
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(endpoint_url)
            context = browser.contexts[0]
            page = context.pages[0]
            page.goto(LANDMARK_SEARCH_URL, timeout=60_000)
            page.wait_for_load_state("networkidle", timeout=60_000)
            sb.sleep(2)
            sb.solve_captcha()
            sb.wait_for_element_absent("input[disabled]")  # wait until form inputs are enabled
            sb.sleep(2)
            page.evaluate(
                """([doctypeIds, begin, end]) => {
                    document.querySelector('#documentTypeIds-DocumentType').value = doctypeIds;
                    document.querySelector('#beginDate-DocumentType').value = begin;
                    document.querySelector('#endDate-DocumentType').value = end;
                }""",
                [doctype_ids, start_date.strftime("%m/%d/%Y"), end_date.strftime("%m/%d/%Y")],
            )
            # Use JS click to bypass Playwright's visibility check — the button can be
            # obscured by a fading CAPTCHA overlay while still being functional.
            page.evaluate("document.querySelector('#submit-DocumentType').click()")
            page.wait_for_load_state("networkidle", timeout=60_000)
            rows = _extract_rows(page)
            return _parse_rows(rows, signal=signal, city_variants=city_variants,
                               start_date=start_date)
    finally:
        sb.quit()


def _extract_rows(page) -> list[dict]:
    """Extract result rows from the Landmark results table."""
    rows = []
    for tr in page.query_selector_all("#resultsTable tbody tr"):
        cells = tr.query_selector_all("td")
        if len(cells) < 5:  # need all 5 columns: recnum, doctype, date, grantor, grantee
            continue
        rows.append({
            "recording_number": cells[0].inner_text().strip(),
            "doc_type":         cells[1].inner_text().strip(),
            "recorded_date":    cells[2].inner_text().strip(),
            "grantor":          cells[3].inner_text().strip(),
            "grantee":          cells[4].inner_text().strip(),
        })
    return rows


def _parse_rows(
    rows: list[dict],
    *,
    signal: str,
    city_variants: set[str],
    start_date: date,
) -> tuple[list, list]:
    """Convert Landmark result rows into candidates.

    NOTE: Landmark results do NOT include address/city/zip. All results go to
    candidates with missing_parcel_id so parcel_enrichment can look them up later.
    City filtering is best-effort from the grantor name — we include all results
    and rely on parcel_enrichment + human review to filter by city.
    """
    candidates = []
    for row in rows:
        rec_date = row.get("recorded_date", start_date.isoformat())
        candidates.append({
            "property_address": "",   # not in Landmark results grid
            "parcel_id":        "",
            "case_id":          row.get("recording_number", ""),
            "signals":          [signal],
            "rejection_reason": "missing_parcel_id",
            "source_url":       LANDMARK_DETAIL_BASE + row.get("recording_number", ""),
            "recorded_date":    _parse_date(rec_date),
            "notes":            (
                f"Grantor: {row.get('grantor', '')}; "
                f"Grantee: {row.get('grantee', '')}; "
                f"Type: {row.get('doc_type', '')}"
            ),
        })
    return [], candidates


def _parse_date(raw: str) -> str:
    """Parse M/D/YYYY or YYYY-MM-DD date string to ISO YYYY-MM-DD."""
    raw = raw.strip()
    # Try M/D/YYYY format first
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if m:
        mo, d, yr = m.groups()
        return f"{yr}-{int(mo):02d}-{int(d):02d}"
    # Already ISO
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]
    fallback = date.today().isoformat()
    if raw:
        print(f"[recorder_direct] _parse_date: unrecognized date format {raw!r}, defaulting to {fallback}")
    return fallback
