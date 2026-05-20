from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class SignalEvent:
    name: str
    tier: str
    source: str = ""
    source_url: str = ""
    recorded_date: str = ""
    case_id: str = ""
    notes: str = ""


@dataclass
class PropertyLead:
    owner: str
    property_address: str
    parcel_id: str
    events: list[SignalEvent] = field(default_factory=list)

    def tier_map(self) -> dict[str, list[str]]:
        tiers: dict[str, list[str]] = {}
        for event in self.events:
            tiers.setdefault(event.tier, [])
            if event.name not in tiers[event.tier]:
                tiers[event.tier].append(event.name)
        return {tier: sorted(names) for tier, names in sorted(tiers.items())}


@dataclass(frozen=True)
class Qualification:
    outreach_qualifying: bool
    confidence: str
    reason: str


@dataclass(frozen=True)
class HuntResult:
    accessed_date: date
    properties: list[PropertyLead]
