from unittest.mock import patch
from realtorfarm.collectors.legal_notices import collect_legal_notices, LEGAL_NOTICE_SOURCES


KENT_NOTS_MARKDOWN = """
# Legal Notices — South County Journal

## Notice of Trustee's Sale

TS No.: KENT-2026-0099

Grantor: KENT TEST OWNER LLC

Property Address: 220 4th Ave S, Kent, WA 98032

Parcel No. 232204-9001

Recorded on May 20, 2026 as Instrument No. 20260520000099.
"""

BURIEN_NOTS_MARKDOWN = """
# Legal Notices

## Notice of Trustee's Sale TS No.: BUR-2026-0042

Grantor: BURIEN SAMPLE OWNER

Property Address: 12345 6th Ave SW, Burien, WA 98146

APN: 123450-0678

Recorded on May 20, 2026.
"""


def test_collect_legal_notices_returns_records_for_kent():
    with patch("realtorfarm.collectors.legal_notices.scrape_url", return_value=KENT_NOTS_MARKDOWN):
        records, candidates = collect_legal_notices(city="Kent", lookback_days=30)

    assert any(r["signal"] == "NOTS" and "Kent" in r["property_address"] for r in records)


def test_collect_legal_notices_filters_to_target_city():
    with patch("realtorfarm.collectors.legal_notices.scrape_url", return_value=BURIEN_NOTS_MARKDOWN):
        records, _ = collect_legal_notices(city="Kent", lookback_days=30)

    assert records == [], "Burien notices must not appear in Kent results"


def test_collect_legal_notices_returns_candidates_for_enrichment():
    # Notice has signal + city mention but no parcel ID
    no_parcel_markdown = """
    Notice of Trustee's Sale TS No.: KENT-2026-0100
    Property Address: 310 W Meeker St, Kent, WA 98032
    Grantor: NO PARCEL OWNER LLC
    Recorded May 21, 2026.
    """

    with patch("realtorfarm.collectors.legal_notices.scrape_url", return_value=no_parcel_markdown):
        _, candidates = collect_legal_notices(city="Kent", lookback_days=30)

    enrichable = [c for c in candidates if c["rejection_reason"] == "missing_parcel_id"]
    assert len(enrichable) >= 1


def test_legal_notice_sources_list_is_nonempty():
    assert len(LEGAL_NOTICE_SOURCES) >= 2
    assert all(src.startswith("https://") for src in LEGAL_NOTICE_SOURCES)
