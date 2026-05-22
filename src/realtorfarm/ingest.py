from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from .models import ListingStatus, PropertyLead, SignalEvent
from .signals import normalize_signal

REQUIRED_COLUMNS = {"owner", "property_address", "parcel_id", "signal"}
DEFAULT_MAX_RECORDS = 99
DEFAULT_LOOKBACK_DAYS = 10


def parse_recorded_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def filter_records(
    records: list[dict[str, str]],
    *,
    accessed: date,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> list[dict[str, str]]:
    """Keep only recent records and cap extraction below 100 by default."""
    if lookback_days < 0:
        raise ValueError("lookback_days must be >= 0")
    if max_records < 1:
        raise ValueError("max_records must be >= 1")
    earliest = accessed - timedelta(days=lookback_days)
    recent: list[dict[str, str]] = []
    for row in records:
        recorded = parse_recorded_date(row.get("recorded_date", ""))
        if recorded is not None and earliest <= recorded <= accessed:
            recent.append(row)
        if len(recent) >= max_records:
            break
    return recent


def load_records(path: str | Path) -> list[dict[str, str]]:
    path = Path(path)
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("JSON input must be a list of record objects")
        return [{str(k): "" if v is None else str(v) for k, v in row.items()} for row in data]
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required columns: {sorted(missing)}")
        return [{k: (v or "").strip() for k, v in row.items()} for row in reader]


def group_records(records: list[dict[str, str]]) -> list[PropertyLead]:
    grouped: dict[tuple[str, str], PropertyLead] = {}
    for row in records:
        name, tier = normalize_signal(row["signal"])
        parcel_id = row.get("parcel_id", "").strip()
        address = row.get("property_address", "").strip()
        owner = row.get("owner", "").strip()
        if not parcel_id or not address:
            raise ValueError(f"Record requires parcel_id and property_address: {row}")
        key = (parcel_id, address.lower())
        lead = grouped.setdefault(key, PropertyLead(owner=owner, property_address=address, parcel_id=parcel_id))
        if owner and owner not in lead.owner:
            lead.owner = f"{lead.owner}; {owner}" if lead.owner else owner
        row_listing = _listing_status_from_row(row)
        if row_listing and lead.listing_status is None:
            lead.listing_status = row_listing
        lead.events.append(
            SignalEvent(
                name=name, tier=tier, source=row.get("source", ""),
                source_url=row.get("source_url", ""), recorded_date=row.get("recorded_date", ""),
                case_id=row.get("case_id", ""), notes=row.get("notes", ""),
            )
        )
    return list(grouped.values())


def load_leads(path: str | Path) -> list[PropertyLead]:
    return group_records(load_records(path))


def _listing_status_from_row(row: dict[str, str]) -> ListingStatus | None:
    listed_status = row.get("listed_status", "").strip()
    listing_date = row.get("listing_date", "").strip()
    listing_url = row.get("listing_url", "").strip()
    listing_source = row.get("listing_source", "").strip()
    if not any((listed_status, listing_date, listing_url, listing_source)):
        return None
    return ListingStatus(
        listed_status=listed_status,
        listing_date=listing_date,
        listing_url=listing_url,
        listing_source=listing_source,
    )
