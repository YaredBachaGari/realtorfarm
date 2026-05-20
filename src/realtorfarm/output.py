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
