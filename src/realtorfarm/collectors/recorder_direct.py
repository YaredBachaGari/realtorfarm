"""Collect NOTS from King County Recorder Landmark Web using Playwright + 2captcha.

Landmark enforces reCAPTCHA v2 on all searches; 2captcha solves it programmatically.
Results come back as AJAX HTML; we parse the results table directly.

Required env vars:
  RECORDER_DIRECT_ENABLED=true   — must be explicitly enabled
  TWOCAPTCHA_API_KEY=<key>       — 2captcha API key for reCAPTCHA solving
"""
from __future__ import annotations

import os
import re
from datetime import date, timedelta

from playwright.sync_api import sync_playwright
from twocaptcha import TwoCaptcha

LANDMARK_SEARCH_URL = (
    "https://recordsearch.kingcounty.gov/LandmarkWeb/search/index"
    "?theme=.blue&section=searchCriteriaDocType&quickSearchSelection="
)
LANDMARK_DOCTYPE_ENDPOINT = (
    "https://recordsearch.kingcounty.gov/LandmarkWeb/Search/DocumentTypeSearch"
)
LANDMARK_DETAIL_BASE = "https://recordsearch.kingcounty.gov/LandmarkWeb/Document/Index/"

# Discovered from page inspection — stable for this site
_RECAPTCHA_SITE_KEY = "6LePF5clAAAAAHUGpyT_rrTZl48-STa5Rn6_PMTv"

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

    twocaptcha_key = os.environ.get("TWOCAPTCHA_API_KEY", "")
    if not twocaptcha_key:
        raise ValueError("TWOCAPTCHA_API_KEY is required when RECORDER_DIRECT_ENABLED=true")

    end_date = date.today()
    start_date = end_date - timedelta(days=lookback_days)
    city_variants = _CITY_VARIANTS.get(city.lower(), {city.lower()})

    records: list[dict[str, str]] = []
    candidates: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for doctype_ids, signal in _DOC_TYPES:
                try:
                    r, c = _search_doc_type(
                        browser=browser,
                        twocaptcha_key=twocaptcha_key,
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
        finally:
            browser.close()

    return records, candidates


def _search_doc_type(
    *,
    browser,
    twocaptcha_key: str,
    doctype_ids: str,
    signal: str,
    city_variants: set[str],
    start_date: date,
    end_date: date,
) -> tuple[list, list]:
    """Run one document-type search via Playwright + 2captcha."""
    page = browser.new_page()
    try:
        page.goto(LANDMARK_SEARCH_URL, timeout=60_000)
        page.wait_for_load_state("networkidle", timeout=60_000)

        # Solve reCAPTCHA
        solver = TwoCaptcha(twocaptcha_key)
        result = solver.recaptcha(
            sitekey=_RECAPTCHA_SITE_KEY,
            url=LANDMARK_SEARCH_URL,
        )
        token = result["code"]

        # Inject captcha token and submit via JavaScript
        page.evaluate(f"""
            document.querySelector('textarea[name="g-recaptcha-response"]').value = `{token}`;
            document.querySelector('#documentTypeIds-DocumentType').value = '{doctype_ids}';
            document.querySelector('#beginDate-DocumentType').value = '{start_date.strftime('%m/%d/%Y')}';
            document.querySelector('#endDate-DocumentType').value = '{end_date.strftime('%m/%d/%Y')}';
        """)
        page.click("#submit-DocumentType")
        page.wait_for_load_state("networkidle", timeout=60_000)

        # Parse results
        rows = _extract_rows(page)
        return _parse_rows(rows, signal=signal, city_variants=city_variants,
                           start_date=start_date)
    finally:
        page.close()


def _extract_rows(page) -> list[dict]:
    """Extract result rows from the Landmark results table."""
    rows = []
    for tr in page.query_selector_all("#resultsTable tbody tr"):
        cells = tr.query_selector_all("td")
        if len(cells) < 4:
            continue
        rows.append({
            "recording_number": cells[0].inner_text().strip() if cells[0] else "",
            "doc_type":         cells[1].inner_text().strip() if len(cells) > 1 else "",
            "recorded_date":    cells[2].inner_text().strip() if len(cells) > 2 else "",
            "grantor":          cells[3].inner_text().strip() if len(cells) > 3 else "",
            "grantee":          cells[4].inner_text().strip() if len(cells) > 4 else "",
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
    return date.today().isoformat()
