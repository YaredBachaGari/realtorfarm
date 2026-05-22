from __future__ import annotations

import json
from datetime import date

from .models import PropertyLead
from .scoring import qualify_property, sort_leads


def lead_to_dict(lead: PropertyLead, include_research: bool = False) -> dict:
    data = {
        "Owner": lead.owner,
        "property address": lead.property_address,
        "parcel id": lead.parcel_id,
        "Signals": lead.tier_map(),
    }
    if include_research:
        q = qualify_property(lead)
        data["outreach_qualifying"] = q.outreach_qualifying
        data["confidence"] = q.confidence
        data["qualification_reason"] = q.reason
        data["lead_status"] = lead_status(lead)
        data["evidence"] = [event.__dict__ for event in lead.events]
    return data


def render_data(leads: list[PropertyLead], accessed: date | None = None, qualified_only: bool = True, include_research: bool = False) -> str:
    accessed = accessed or date.today()
    chosen = sort_leads(leads)
    if qualified_only:
        chosen = [lead for lead in chosen if qualify_property(lead).outreach_qualifying]
    payload = {
        "accessed_date": accessed.strftime("%m/%d/%Y"),
        "properties": [lead_to_dict(lead, include_research=include_research) for lead in chosen],
    }
    return "data= " + json.dumps(payload, indent=2, ensure_ascii=False)


def lead_status(lead: PropertyLead) -> dict:
    """Return the market/listing label without excluding the lead."""
    first_distress_date = _first_recorded_date(lead)
    listing = lead.listing_status
    if listing is None:
        return {
            "market_label": "listing_status_unknown",
            "first_distress_recorded_date": first_distress_date or "",
            "decision": "needs_listing_status_check",
        }

    status = {
        "market_label": "listing_status_unknown",
        "listed_status": listing.listed_status,
        "listing_date": listing.listing_date,
        "first_distress_recorded_date": first_distress_date or "",
        "listing_url": listing.listing_url,
        "listing_source": listing.listing_source,
        "decision": "keep_labeled_do_not_exclude",
    }
    if listing.listed_status.strip().lower() in {"not_listed", "not listed", "off_market", "off market"}:
        status["market_label"] = "pre_market_candidate"
        return status

    listing_date = _parse_iso_date(listing.listing_date)
    distress_date = _parse_iso_date(first_distress_date or "")
    if listing_date and distress_date:
        days = (distress_date - listing_date).days
        if days > 0:
            status["market_label"] = "already_listed_before_notice"
            status["days_listing_before_distress_notice"] = days
        elif days == 0:
            status["market_label"] = "listed_same_day_as_notice"
            status["days_listing_before_distress_notice"] = 0
        else:
            status["market_label"] = "listed_after_notice"
            status["days_notice_before_listing"] = abs(days)
    elif listing.listed_status:
        status["market_label"] = "listed_date_unknown"
    return status


def _first_recorded_date(lead: PropertyLead) -> str | None:
    dates = sorted(d for d in (_parse_iso_date(event.recorded_date) for event in lead.events) if d)
    return dates[0].isoformat() if dates else None


def _parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None
