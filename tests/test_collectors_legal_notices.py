from unittest.mock import patch, call
from datetime import date, timedelta
from realtorfarm.collectors.legal_notices import (
    collect_legal_notices,
    _build_sources,
    _DJC_MAX_DAYS,
)


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


# ── _build_sources() ──────────────────────────────────────────────────────────

def test_build_sources_includes_todays_djc_url():
    """lookback_days=1 → exactly one DJC URL containing today's ISO date."""
    today = date.today().isoformat()
    sources = _build_sources(1)
    djc = [s for s in sources if "djc.com" in s]
    assert len(djc) == 1
    assert today in djc[0]


def test_build_sources_respects_lookback_days():
    """lookback_days=3 → three DJC date URLs (today, yesterday, two days ago)."""
    sources = _build_sources(3)
    djc = [s for s in sources if "djc.com" in s]
    assert len(djc) == 3
    for i in range(3):
        expected_date = (date.today() - timedelta(days=i)).isoformat()
        assert any(expected_date in s for s in djc)


def test_build_sources_caps_djc_at_max_days():
    """lookback_days=30 → DJC capped at _DJC_MAX_DAYS, not 30 calls."""
    sources = _build_sources(30)
    djc = [s for s in sources if "djc.com" in s]
    assert len(djc) == _DJC_MAX_DAYS


def test_build_sources_all_https():
    """Every URL in _build_sources() starts with https://."""
    assert all(s.startswith("https://") for s in _build_sources(1))


# ── collect_legal_notices() ───────────────────────────────────────────────────

def test_collect_legal_notices_returns_records_for_kent(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    with patch("realtorfarm.collectors.legal_notices.scrape_url", return_value=KENT_NOTS_MARKDOWN):
        records, candidates = collect_legal_notices(city="Kent", lookback_days=1)

    assert any(r["signal"] == "NOTS" and "Kent" in r["property_address"] for r in records)


def test_collect_legal_notices_filters_to_target_city(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    with patch("realtorfarm.collectors.legal_notices.scrape_url", return_value=BURIEN_NOTS_MARKDOWN):
        records, _ = collect_legal_notices(city="Kent", lookback_days=1)

    assert records == [], "Burien notices must not appear in Kent results"


def test_collect_legal_notices_returns_candidates_for_enrichment(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    no_parcel_markdown = """
    Notice of Trustee's Sale TS No.: KENT-2026-0100
    Property Address: 310 W Meeker St, Kent, WA 98032
    Grantor: NO PARCEL OWNER LLC
    Recorded May 21, 2026.
    """
    with patch("realtorfarm.collectors.legal_notices.scrape_url", return_value=no_parcel_markdown):
        _, candidates = collect_legal_notices(city="Kent", lookback_days=1)

    enrichable = [c for c in candidates if c["rejection_reason"] == "missing_parcel_id"]
    assert len(enrichable) >= 1


def test_collect_legal_notices_calls_scrape_url_per_source(monkeypatch):
    """One scrape_url call per URL returned by _build_sources(lookback_days)."""
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    expected_count = len(_build_sources(1))
    with patch("realtorfarm.collectors.legal_notices.scrape_url", return_value="") as mock_scrape:
        collect_legal_notices(city="Kent", lookback_days=1)

    assert mock_scrape.call_count == expected_count
