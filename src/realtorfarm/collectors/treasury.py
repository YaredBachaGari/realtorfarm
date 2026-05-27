"""Collect Tax Delinquent 3+ Years signal from King County Treasury page via direct HTTP fetch."""
from __future__ import annotations

import re
from datetime import date

from .firecrawl import scrape_url

TREASURY_URL = (
    "https://kingcounty.gov/en/dept/executive-services/buildings-property/"
    "treasury-operations/tax-foreclosures"
)

_PARCEL_RE = re.compile(r"\b([0-9]{6}-[0-9]{4}(?:-[0-9]{2})?)\b")


def collect_treasury(*, city: str) -> list[dict[str, str]]:
    """Return canonical Tax Delinquent rows for target city from King County Treasury page."""
    try:
        text = scrape_url(TREASURY_URL)
    except Exception as exc:
        print(f"[treasury] fetch failed: {exc}")
        return []

    return _parse_treasury_text(text, city=city)


def _parse_treasury_text(text: str, *, city: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    city_re = re.compile(
        rf"\b{re.escape(city)}\b[^|\n]{{0,60}}WA\s+\d{{5}}", re.I
    )

    for line in text.splitlines():
        if not city_re.search(line):
            continue
        parcel_match = _PARCEL_RE.search(line)
        if not parcel_match:
            continue
        parcel_id = parcel_match.group(1)
        address = _extract_address_from_line(line, city=city)
        owner = _extract_owner_from_line(line)
        records.append({
            "owner": owner,
            "property_address": address,
            "parcel_id": parcel_id,
            "signal": "Tax Delinquent 3+ Years Free-and-Clear",
            "source": "King County Treasury tax foreclosure",
            "source_url": TREASURY_URL,
            "recorded_date": date.today().isoformat(),
            "case_id": "",
            "notes": "Tax delinquent 3+ years per King County Treasury foreclosure list",
        })
    return records


def _extract_address_from_line(line: str, *, city: str) -> str:
    city_re = re.compile(
        rf"(\d{{1,6}}\s+[^|]{{2,60}}?\b{re.escape(city)}\b[^|]{{0,30}}WA\s+\d{{5}}(?:-\d{{4}})?)",
        re.I,
    )
    m = city_re.search(line)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _extract_owner_from_line(line: str) -> str:
    # Markdown table rows: | parcel | owner | address | years |
    parts = [p.strip() for p in line.split("|") if p.strip()]
    if len(parts) >= 2:
        return parts[1].upper()
    print(f"[treasury] could not extract owner from line (no pipe-delimited columns): {line[:80]!r}")
    return "UNKNOWN OWNER"
