from realtorfarm.ingest import group_records
from realtorfarm.scoring import qualify_property


def lead_with(*signals):
    rows = [
        {"owner": "Owner", "property_address": "1 Main St, Burien, WA", "parcel_id": "1", "signal": sig}
        for sig in signals
    ]
    return group_records(rows)[0]


def test_tier_1_always_qualifies():
    q = qualify_property(lead_with("NOTS"))
    assert q.outreach_qualifying is True
    assert q.confidence == "very_high"


def test_single_tier_2_qualifies():
    q = qualify_property(lead_with("NOD"))
    assert q.outreach_qualifying is True
    assert q.confidence == "high"


def test_two_tier_3_signals_qualify():
    q = qualify_property(lead_with("Eviction", "Death of Owner"))
    assert q.outreach_qualifying is True
    assert q.confidence == "medium"


def test_weak_tier_4_alone_does_not_qualify():
    q = qualify_property(lead_with("Absentee Ownership", "Vacant Property"))
    assert q.outreach_qualifying is False
    assert q.confidence == "context_only"
