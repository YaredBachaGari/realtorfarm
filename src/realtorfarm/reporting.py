from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from .ingest import filter_records, group_records, load_records, parse_recorded_date
from .scoring import qualify_property


def build_source_report(
    *,
    city: str,
    input_path: str | Path,
    accessed_date: str | date,
    lookback_days: int,
    max_records: int,
) -> dict[str, Any]:
    """Build an observability report explaining why a city feed did/didn't emit leads."""
    accessed = date.fromisoformat(accessed_date) if isinstance(accessed_date, str) else accessed_date
    raw_records = load_records(input_path)
    accepted_records = filter_records(
        raw_records,
        accessed=accessed,
        lookback_days=lookback_days,
        max_records=max_records,
    )
    accepted_ids = {_record_identity(row) for row in accepted_records}

    rejected_date_window = 0
    rejected_missing_or_invalid_date = 0
    accepted_counter: Counter[str] = Counter()
    raw_counter: Counter[str] = Counter()
    date_window_counter: Counter[str] = Counter()
    invalid_date_counter: Counter[str] = Counter()

    earliest = accessed.toordinal() - lookback_days
    latest = accessed.toordinal()
    for row in raw_records:
        source = _source_name(row)
        raw_counter[source] += 1
        recorded = parse_recorded_date(row.get("recorded_date", ""))
        identity = _record_identity(row)
        if identity in accepted_ids:
            accepted_counter[source] += 1
        elif recorded is None:
            rejected_missing_or_invalid_date += 1
            invalid_date_counter[source] += 1
        elif not (earliest <= recorded.toordinal() <= latest):
            rejected_date_window += 1
            date_window_counter[source] += 1

    leads = group_records(accepted_records)
    qualifying = sum(1 for lead in leads if qualify_property(lead).outreach_qualifying)

    per_source_leads: dict[str, list] = defaultdict(list)
    for source, rows in _records_by_source(accepted_records).items():
        per_source_leads[source] = group_records(rows)

    sources = []
    for source in sorted(raw_counter):
        source_leads = per_source_leads.get(source, [])
        sources.append(
            {
                "name": source,
                "raw_records": raw_counter[source],
                "accepted_records": accepted_counter[source],
                "rejected_date_window": date_window_counter[source],
                "rejected_missing_or_invalid_date": invalid_date_counter[source],
                "properties": len(source_leads),
                "outreach_qualifying": sum(
                    1 for lead in source_leads if qualify_property(lead).outreach_qualifying
                ),
            }
        )

    return {
        "city": city,
        "accessed_date": accessed.isoformat(),
        "lookback_days": lookback_days,
        "max_records": max_records,
        "pipeline_status": _pipeline_status(len(raw_records), len(accepted_records), qualifying),
        "recommended_next_action": _recommended_next_action(len(raw_records), len(accepted_records), qualifying),
        "input": {
            "path": str(input_path),
            "raw_records": len(raw_records),
            "accepted_records": len(accepted_records),
            "rejected_date_window": rejected_date_window,
            "rejected_missing_or_invalid_date": rejected_missing_or_invalid_date,
            "capped": len(accepted_records) >= max_records,
        },
        "output": {
            "properties": len(leads),
            "outreach_qualifying": qualifying,
        },
        "sources": sources,
    }


def _source_name(row: dict[str, str]) -> str:
    return row.get("source", "").strip() or "unknown"


def _pipeline_status(raw_count: int, accepted_count: int, qualifying_count: int) -> str:
    if raw_count == 0:
        return "empty_collector_feed"
    if accepted_count == 0:
        return "raw_records_rejected_by_date_or_required_fields"
    if qualifying_count == 0:
        return "records_found_but_not_outreach_qualifying"
    return "active_records_found"


def _recommended_next_action(raw_count: int, accepted_count: int, qualifying_count: int) -> str:
    if raw_count == 0:
        return "populate_and_verify_source collectors; do not interpret zero rows as zero market distress"
    if accepted_count == 0:
        return "inspect date-window and required-field rejections before relaxing qualification rules"
    if qualifying_count == 0:
        return "add corroborating source enrichment before outreach"
    return "run listing-status labeling and prioritize pre-market leads"


def _record_identity(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return (
        row.get("parcel_id", ""),
        row.get("property_address", ""),
        row.get("signal", ""),
        row.get("case_id", ""),
        row.get("source_url", ""),
    )


def _records_by_source(records: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in records:
        grouped[_source_name(row)].append(row)
    return dict(grouped)
