import json
from datetime import date

from realtorfarm.ingest import group_records
from realtorfarm.output import render_data
from realtorfarm.extractors.public_notices import extract_notice_records


def payload_from_rendered(text: str) -> dict:
    return json.loads(text.removeprefix("data= "))


def test_render_keeps_already_listed_leads_and_labels_them():
    leads = group_records([
        {
            "owner": "12203 DMM LLC",
            "property_address": "12215 Des Moines Memorial Drive S Unit B, Burien, WA 98168",
            "parcel_id": "8944030060",
            "signal": "NOTS",
            "source": "public legal notice",
            "source_url": "file:///notice.txt",
            "recorded_date": "2026-05-11",
            "case_id": "20260511000326",
            "notes": "notice",
            "listed_status": "active",
            "listing_date": "2026-03-02",
            "listing_url": "https://www.zillow.com/example",
            "listing_source": "Zillow/NWMLS",
        }
    ])

    payload = payload_from_rendered(render_data(leads, accessed=date(2026, 5, 22), include_research=True))

    assert len(payload["properties"]) == 1
    assert payload["properties"][0]["lead_status"] == {
        "market_label": "already_listed_before_notice",
        "listed_status": "active",
        "listing_date": "2026-03-02",
        "first_distress_recorded_date": "2026-05-11",
        "days_listing_before_distress_notice": 70,
        "listing_url": "https://www.zillow.com/example",
        "listing_source": "Zillow/NWMLS",
        "decision": "keep_labeled_do_not_exclude",
    }


def test_render_labels_unknown_listing_status_for_unchecked_leads():
    leads = group_records([
        {
            "owner": "Owner",
            "property_address": "12345 6th Ave SW, Burien, WA 98146",
            "parcel_id": "1234500678",
            "signal": "NOTS",
            "source": "public legal notice",
            "source_url": "file:///notice.txt",
            "recorded_date": "2026-05-11",
            "case_id": "case",
            "notes": "notice",
        }
    ])

    payload = payload_from_rendered(render_data(leads, accessed=date(2026, 5, 22), include_research=True))

    assert payload["properties"][0]["lead_status"]["market_label"] == "listing_status_unknown"
    assert payload["properties"][0]["lead_status"]["decision"] == "needs_listing_status_check"


def test_render_labels_not_listed_leads_as_pre_market_candidates():
    leads = group_records([
        {
            "owner": "Owner",
            "property_address": "12345 6th Ave SW, Burien, WA 98146",
            "parcel_id": "1234500678",
            "signal": "NOTS",
            "source": "public legal notice",
            "source_url": "file:///notice.txt",
            "recorded_date": "2026-05-11",
            "case_id": "case",
            "notes": "notice",
            "listed_status": "not_listed",
            "listing_source": "MLS/Zillow check",
        }
    ])

    payload = payload_from_rendered(render_data(leads, accessed=date(2026, 5, 22), include_research=True))

    assert payload["properties"][0]["lead_status"]["market_label"] == "pre_market_candidate"
    assert payload["properties"][0]["lead_status"]["decision"] == "keep_labeled_do_not_exclude"


def test_notice_parser_matches_multi_parcel_document_to_exact_unit():
    records = extract_notice_records(
        """
        Document Type: AMENDED NOTICE OF TRUSTEE SALE
        Recording Date: 05/11/2026
        Recording Number: 20260511000326
        Grantor: 12203 DMM LLC
        Legal/Parcel: PID: 8944030050 Unit A; PID: 8944030060 Unit B; SUB: VILLA TOWNHOMES
        Property Address: 12215 Des Moines Memorial Drive S Unit B, Burien, WA 98168
        """,
        source_url="file:///notice.txt",
        target_city="Burien",
    )

    assert records[0]["parcel_id"] == "8944030060"
