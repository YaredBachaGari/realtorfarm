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


def pin_to_formatted(pin: str) -> str:
    """Normalize any KC parcel PIN to dash-separated display format XXXXXX-XXXX."""
    raw = pin.replace("-", "")
    if len(raw) < 10:
        raw = raw.zfill(10)
    return f"{raw[:6]}-{raw[6:10]}"


def format_address(attrs: dict) -> str:
    """Build a canonical situs address string from KC GIS parcel attributes dict."""
    street = attrs.get("ADDR_FULL", "").strip().title()
    city = attrs.get("CTYNAME", "").strip().title()
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
    resp = requests.get(KCGIS_PARCEL_LAYER, params={
        "where": f"PIN = '{pin_clean}'",
        "outFields": "PIN,ADDR_FULL,CTYNAME,ZIP5",
        "returnGeometry": "false",
        "f": "json",
    }, timeout=timeout)
    resp.raise_for_status()
    features = resp.json().get("features", [])
    return features[0]["attributes"] if features else None


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
    features = resp.json().get("features", [])
    return features[0]["attributes"] if features else None


def _normalize_street(address: str) -> str:
    """Extract and uppercase the street portion of *address* for an ArcGIS LIKE query."""
    street = address.split(",")[0].strip().upper()
    for long_form, abbrev in _STREET_TYPE_MAP.items():
        street = re.sub(rf"\b{long_form}\b", abbrev, street)
    return street.replace("'", "''")
