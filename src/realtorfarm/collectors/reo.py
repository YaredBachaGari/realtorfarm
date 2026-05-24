"""Collect REO (bank-owned) properties from HUD Home Store and lender portals."""
from __future__ import annotations

import os
import re

from .browser_use import run_task
from .firecrawl import scrape_url

# City → zip code mapping for King County target cities
_CITY_ZIPS: dict[str, list[str]] = {
    "burien":  ["98146", "98148", "98166", "98168"],
    "kent":    ["98030", "98031", "98032", "98042"],
    "tukwila": ["98168", "98188"],
}

_PARCEL_RE = re.compile(r"\b([0-9]{6}-[0-9]{4}(?:-[0-9]{2})?)\b")
_PRICE_RE  = re.compile(r"\$\s*([0-9]{1,3}(?:,\d{3})*(?:\.\d{2})?)")
_ADDRESS_RE = re.compile(
    r"(\d{1,6}\s+[^\n.;]{2,80}?\b(?:Ave|St|Rd|Dr|Ln|Ct|Pl|Way|Blvd)\b[^\n]{0,60}WA\s+\d{5})",
    re.I,
)

_HUD_URL = "https://www.hudhomestore.gov/Listing/PropList.aspx?sState=WA&sZip={zip}"

# (source_key, starting_url, display_name)
_BROWSER_SOURCES: list[tuple[str, str, str]] = [
    ("homepath",   "https://www.homepath.com/",                               "Fannie Mae HomePath"),
    ("homesteps",  "https://www.homesteps.com/",                              "Freddie Mac HomeSteps"),
    ("wellsfargo", "https://reo.wellsfargo.com/",                             "Wells Fargo REO"),
    ("chase",      "https://www.chase.com/mortgage/real-estate-owned",        "Chase REO"),
    ("bofa",       "https://realestate.bankofamerica.com/reo",                "Bank of America REO"),
    ("citi",       "https://www.citimortgage.com/mortgage/real-estate-owned", "Citi REO"),
]


def collect_reo(
    *, city: str, lookback_days: int = 1
) -> tuple[list[dict[str, str]], list[dict]]:
    """Return REO canonical records and candidates for *city*.

    *lookback_days* is accepted for interface consistency but not used —
    REO portals show current inventory, not a dated feed.
    """
    if os.environ.get("REO_ENABLED", "").lower() != "true":
        return [], []

    zips = _CITY_ZIPS.get(city.lower(), [])
    records: list[dict[str, str]] = []
    candidates: list[dict] = []

    # HUD Home Store — one Firecrawl call per zip
    hud_r, hud_c = _collect_hud(city=city, zips=zips)
    records.extend(hud_r)
    candidates.extend(hud_c)

    # Lender portals — Browser Use, capped by REO_BROWSER_USE_MAX_TASKS
    max_tasks = int(os.environ.get("REO_BROWSER_USE_MAX_TASKS", "6"))
    tasks_run = 0
    for _key, url, source_name in _BROWSER_SOURCES:
        if tasks_run >= max_tasks:
            break
        try:
            r, c = _collect_browser_source(city=city, url=url, source_name=source_name)
            records.extend(r)
            candidates.extend(c)
        except (RuntimeError, TimeoutError, OSError, ValueError) as exc:
            print(f"[reo] {source_name} task failed for {city}: {exc}")
        tasks_run += 1

    records, candidates = _deduplicate(records, candidates)
    return records, candidates


# ── Source collectors ─────────────────────────────────────────────────────────

def _collect_hud(*, city: str, zips: list[str]) -> tuple[list[dict[str, str]], list[dict]]:
    records: list[dict[str, str]] = []
    candidates: list[dict] = []
    for zip_code in zips:
        url = _HUD_URL.format(zip=zip_code)
        try:
            text = scrape_url(url)
            if not text.strip():
                print(f"[reo] no HUD listings for zip {zip_code}")
                continue
            r, c = _parse_hud_text(text, city=city, source_url=url)
            records.extend(r)
            candidates.extend(c)
        except (RuntimeError, TimeoutError, OSError, ValueError) as exc:
            print(f"[reo] HUD zip {zip_code} failed: {exc}")
    return records, candidates


def _collect_browser_source(
    *, city: str, url: str, source_name: str
) -> tuple[list[dict[str, str]], list[dict]]:
    task = (
        f"Go to {url} and search for REO / bank-owned properties in {city}, WA. "
        f"Return each listing as: address, property ID or loan number if shown. "
        f"One property per line."
    )
    text = run_task(task)
    if not text.strip():
        print(f"[reo] no listings found for {source_name} in {city}")
        return [], []
    return _parse_portal_text(text, city=city, source_name=source_name, source_url=url)


# ── Parsers ───────────────────────────────────────────────────────────────────

def _parse_hud_text(
    text: str, *, city: str, source_url: str
) -> tuple[list[dict[str, str]], list[dict]]:
    """Parse Firecrawl markdown from HUD Home Store into records/candidates."""
    records: list[dict[str, str]] = []
    candidates: list[dict] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        block = block.strip()
        if not block:
            continue
        address   = _extract_address(block, city=city)
        parcel_id = _extract_parcel(block)
        case_id   = _extract_case_id(block)
        price     = _extract_price(block)
        notes     = f"List price: ${price}" if price else ""

        if parcel_id and address:
            records.append({
                "owner":            "HUD",
                "property_address": address,
                "parcel_id":        parcel_id,
                "signal":           "REO",
                "source":           "HUD Home Store",
                "source_url":       source_url,
                "recorded_date":    "",
                "case_id":          case_id,
                "notes":            notes,
            })
        elif address or case_id:
            candidates.append({
                "property_address": address,
                "parcel_id":        parcel_id,
                "case_id":          case_id,
                "signals":          ["REO"],
                "rejection_reason": "missing_parcel_id",
                "source_url":       source_url,
                "recorded_date":    "",
            })
    return records, candidates


def _parse_portal_text(
    text: str, *, city: str, source_name: str, source_url: str
) -> tuple[list[dict[str, str]], list[dict]]:
    """Parse Browser Use output from a lender portal into records/candidates."""
    records: list[dict[str, str]] = []
    candidates: list[dict] = []
    blocks = re.split(r"\n\s*\n", text.strip()) or [text.strip()]
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        address   = _extract_address(block, city=city)
        parcel_id = _extract_parcel(block)
        case_id   = _extract_case_id(block)
        price     = _extract_price(block)
        notes     = f"List price: ${price}" if price else ""

        if parcel_id and address:
            records.append({
                "owner":            source_name,
                "property_address": address,
                "parcel_id":        parcel_id,
                "signal":           "REO",
                "source":           source_name,
                "source_url":       source_url,
                "recorded_date":    "",
                "case_id":          case_id,
                "notes":            notes,
            })
        elif address or case_id:
            candidates.append({
                "property_address": address,
                "parcel_id":        parcel_id,
                "case_id":          case_id,
                "signals":          ["REO"],
                "rejection_reason": "missing_parcel_id",
                "source_url":       source_url,
                "recorded_date":    "",
            })
    return records, candidates


# ── Deduplication ─────────────────────────────────────────────────────────────

def _deduplicate(
    records: list[dict[str, str]],
    candidates: list[dict],
) -> tuple[list[dict[str, str]], list[dict]]:
    """Remove duplicate (address, signal) pairs; first source URL wins."""
    seen: set[tuple[str, str]] = set()
    deduped_records: list[dict[str, str]] = []
    for r in records:
        key = (r["property_address"].lower(), r["signal"])
        if key not in seen:
            seen.add(key)
            deduped_records.append(r)

    deduped_candidates: list[dict] = []
    for c in candidates:
        key = (c.get("property_address", "").lower(), "REO")
        if key not in seen:
            seen.add(key)
            deduped_candidates.append(c)

    return deduped_records, deduped_candidates


# ── Extraction helpers ────────────────────────────────────────────────────────

def _extract_parcel(text: str) -> str:
    m = _PARCEL_RE.search(text)
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


def _extract_case_id(text: str) -> str:
    """Extract HUD case numbers, state-prefixed IDs, or MLS IDs."""
    m = re.search(r"\b(\d{3}-\d{6,})\b", text)           # HUD: 251-123456
    if m:
        return m.group(1)
    m = re.search(r"\b([A-Z]{2}-\d{6,})\b", text)         # State-prefixed: WA-123456
    if m:
        return m.group(1)
    m = re.search(r"\b(MLS[:#\s]*\d{5,})\b", text, re.I)  # MLS: MLS#12345
    if m:
        return m.group(1)
    return ""


def _extract_price(text: str) -> str:
    m = _PRICE_RE.search(text)
    return m.group(1) if m else ""
