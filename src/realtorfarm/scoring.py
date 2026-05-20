from __future__ import annotations

from .models import PropertyLead, Qualification

TIER_ORDER = ("Tier_1", "Tier_2", "Tier_3", "Tier_4")


def qualify_property(lead: PropertyLead) -> Qualification:
    tiers = lead.tier_map()
    t1 = len(tiers.get("Tier_1", []))
    t2 = len(tiers.get("Tier_2", []))
    t3 = len(tiers.get("Tier_3", []))
    t4 = len(tiers.get("Tier_4", []))

    if t1:
        return Qualification(True, "very_high", "Tier 1 forcing event present; always outreach-qualifying.")
    if t2:
        return Qualification(True, "high", "Tier 2 strong distress signal present; qualifying with reasonable confidence.")
    if t3 >= 2:
        return Qualification(True, "medium", "Multiple Tier 3 moderate signals combine into an outreach-qualifying lead.")
    if t3 >= 1 and t4 >= 2:
        return Qualification(True, "medium_low", "Tier 3 signal strengthened by two or more Tier 4 context multipliers.")
    if t3 == 1:
        return Qualification(False, "watch", "Single Tier 3 signal requires another corroborating signal before outreach.")
    if t4:
        return Qualification(False, "context_only", "Tier 4 signals are weak multipliers only, not standalone distress.")
    return Qualification(False, "none", "No configured distress signal detected.")


def sort_leads(leads: list[PropertyLead]) -> list[PropertyLead]:
    def rank(lead: PropertyLead) -> tuple[int, int, str]:
        tiers = lead.tier_map()
        best = min((TIER_ORDER.index(t) for t in tiers), default=99)
        count = sum(len(v) for v in tiers.values())
        return (best, -count, lead.property_address.lower())

    return sorted(leads, key=rank)
