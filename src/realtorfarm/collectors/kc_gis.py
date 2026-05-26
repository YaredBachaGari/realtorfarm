"""King County GIS REST API — free parcel lookup by PIN or address, no auth required.

Confirmed endpoint (2026-05):
  https://gismaps.kingcounty.gov/arcgis/rest/services/Property/KingCo_PropertyInfo/MapServer/2
Fields available: PIN, ADDR_FULL, CTYNAME, ZIP5.
NOTE: owner name is intentionally redacted from all public KC GIS layers.
"""
from __future__ import annotations

import re

import requests

KCGIS_PARCEL_LAYER = (
    "https://gismaps.kingcounty.gov/arcgis/rest/services"
    "/Property/KingCo_PropertyInfo/MapServer/2/query"
)

_STREET_TYPE_MAP = {
    "STREET": "ST", "AVENUE": "AVE", "ROAD": "RD", "DRIVE": "DR",
    "LANE": "LN", "COURT": "CT", "PLACE": "PL", "BOULEVARD": "BLVD",
    "CIRCLE": "CIR", "HIGHWAY": "HWY", "TRAIL": "TRL", "TERRACE": "TER",
}

_DIRECTIONS = re.compile(
    r'\b(Ne|Nw|Se|Sw|N|S|E|W)\b',
    re.IGNORECASE,
)


def _fix_title_case(s: str) -> str:
    """Apply title-case but keep directional abbreviations uppercase.

    Handles ordinal suffixes like ``4TH`` → ``4th`` correctly (Python's
    built-in ``.title()`` treats digits as word boundaries and would produce
    ``4Th``).  Each space-separated token is processed independently: tokens
    that start with digits have their letter suffix fully lowercased (ordinals),
    while all other tokens are capitalised on the first letter only.
    Directional abbreviations (N, S, E, W, NE, NW, SE, SW) are then
    re-uppercased via regex.
    """
    titled = " ".join(_title_word(w) for w in s.strip().split())
    return _DIRECTIONS.sub(lambda m: m.group().upper(), titled)


def _title_word(w: str) -> str:
    """Capitalise one space-separated token correctly."""
    # Ordinal-style token: digits immediately followed by letters, e.g. "4TH"
    m = re.match(r'^(\d+)([A-Za-z]+)$', w)
    if m:
        return m.group(1) + m.group(2).lower()
    # General token: uppercase the first alphabetic character, lowercase rest
    for i, c in enumerate(w):
        if c.isalpha():
            return w[:i] + c.upper() + w[i + 1:].lower()
    return w.lower()


def pin_to_formatted(pin: str) -> str:
    """Normalize any KC parcel PIN to dash-separated display format XXXXXX-XXXX."""
    raw = pin.replace("-", "")
    if len(raw) > 10:
        raise ValueError(f"PIN too long after stripping dashes: {pin!r}")
    if len(raw) < 10:
        raw = raw.zfill(10)
    return f"{raw[:6]}-{raw[6:10]}"


def format_address(attrs: dict) -> str:
    """Build a canonical situs address string from KC GIS parcel attributes dict."""
    street = _fix_title_case(attrs.get("ADDR_FULL", ""))
    city = _fix_title_case(attrs.get("CTYNAME", ""))
    zip5 = attrs.get("ZIP5", "").strip()
    if not street:
        return ""
    parts = [street]
    if city:
        parts.append(city)
    parts.append(f"WA {zip5}" if zip5 else "WA")
    return ", ".join(parts)


def lookup_by_pin(pin: str, *, timeout: int = 15) -> dict | None:
    """Return parcel attribute dict for *pin* (with or without dash), or None."""
    pin_clean = pin.replace("-", "")
    if not re.fullmatch(r"[0-9]{10}", pin_clean):
        raise ValueError(f"Invalid KC PIN (must be 10 digits): {pin!r}")
    resp = requests.get(KCGIS_PARCEL_LAYER, params={
        "where": f"PIN = '{pin_clean}'",
        "outFields": "PIN,ADDR_FULL,CTYNAME,ZIP5",
        "returnGeometry": "false",
        "f": "json",
    }, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"KC GIS API error: {data['error']}")
    features = data.get("features", [])
    if not features:
        return None
    attrs = features[0].get("attributes")
    return attrs if attrs else None


def lookup_by_address(address: str, *, timeout: int = 15) -> dict | None:
    """Return first matching parcel attribute dict for *address*, or None."""
    street = _normalize_street(address)
    if not street:
        return None
    resp = requests.get(KCGIS_PARCEL_LAYER, params={
        "where": f"UPPER(ADDR_FULL) LIKE '%{street}%'",
        "outFields": "PIN,ADDR_FULL,CTYNAME,ZIP5",
        "returnGeometry": "false",
        "f": "json",
    }, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"KC GIS API error: {data['error']}")
    features = data.get("features", [])
    if not features:
        return None
    attrs = features[0].get("attributes")
    return attrs if attrs else None


def _normalize_street(address: str) -> str:
    """Extract and uppercase the street portion of *address* for an ArcGIS LIKE query."""
    street = address.split(",")[0].strip().upper()
    for long_form, abbrev in _STREET_TYPE_MAP.items():
        street = re.sub(rf"\b{long_form}\b\s*$", abbrev, street)
    street = street.replace("'", "''")
    # allowlist: alphanumeric, space, hyphen, hash, slash, apostrophe (already escaped to '')
    street = re.sub(r"[^A-Z0-9 '#/\-]", "", street)
    return street
