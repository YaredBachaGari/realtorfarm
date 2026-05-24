"""Tests for the REO collector."""
import os
from unittest.mock import patch, call

from realtorfarm.collectors.reo import collect_reo, _parse_hud_text


# ── Sample text fixtures ─────────────────────────────────────────────────────

HUD_WITH_PARCEL = """
Property Address: 12345 6th Ave SW, Burien, WA 98146
HUD Case Number: 251-123456
Parcel: 123450-0678
List Price: $185,000
"""

HUD_MISSING_PARCEL = """
Property Address: 999 SW 152nd St, Burien, WA 98166
HUD Case Number: 251-789012
List Price: $210,000
"""

PORTAL_WITH_ADDRESS = """
123 Main St, Burien, WA 98146
Property ID: WF-20260522
"""

# ── Tests ────────────────────────────────────────────────────────────────────

def test_collect_reo_returns_empty_when_disabled():
    """REO_ENABLED not set → returns ([], []) immediately."""
    assert os.environ.get("REO_ENABLED", "") != "true"  # guard: must be unset
    records, candidates = collect_reo(city="Burien", lookback_days=1)
    assert records == []
    assert candidates == []


def test_collect_hud_uses_firecrawl_per_zip(monkeypatch):
    """One scrape_url call per zip code for the target city; Browser Use not called."""
    monkeypatch.setenv("REO_ENABLED", "true")
    monkeypatch.setenv("REO_BROWSER_USE_MAX_TASKS", "0")  # disable Browser Use
    with patch("realtorfarm.collectors.reo.scrape_url", return_value="") as mock_scrape, \
         patch("realtorfarm.collectors.reo.run_task") as mock_run:
        collect_reo(city="Burien", lookback_days=1)
    # Burien has 4 zip codes: 98146, 98148, 98166, 98168
    assert mock_scrape.call_count == 4
    assert mock_run.call_count == 0
    urls_called = [str(c) for c in mock_scrape.call_args_list]
    for zip_code in ["98146", "98148", "98166", "98168"]:
        assert any(zip_code in u for u in urls_called)


def test_parse_hud_output_extracts_canonical_record():
    """HUD text with parcel → canonical record; HUD text without parcel → candidate."""
    records, candidates = _parse_hud_text(
        HUD_WITH_PARCEL,
        city="Burien",
        source_url="https://www.hudhomestore.gov/Listing/PropList.aspx?sState=WA&sZip=98146",
    )
    assert len(records) == 1
    assert records[0]["signal"] == "REO"
    assert records[0]["source"] == "HUD Home Store"
    assert records[0]["property_address"] == "12345 6th Ave SW, Burien, WA 98146"
    assert records[0]["parcel_id"] == "123450-0678"
    assert records[0]["case_id"] == "251-123456"
    assert "185,000" in records[0]["notes"]
    assert candidates == []


def test_collect_browser_use_sources_run_one_task_per_source(monkeypatch):
    """One Browser Use task per portal source (6 sources by default)."""
    monkeypatch.setenv("REO_ENABLED", "true")
    monkeypatch.setenv("REO_BROWSER_USE_MAX_TASKS", "6")
    with patch("realtorfarm.collectors.reo.scrape_url", return_value=""), \
         patch("realtorfarm.collectors.reo.run_task", return_value="") as mock_run:
        collect_reo(city="Kent", lookback_days=1)
    assert mock_run.call_count == 6
    all_tasks = " ".join(str(c) for c in mock_run.call_args_list)
    assert "homepath.com" in all_tasks
    assert "homesteps.com" in all_tasks
    assert "wellsfargo.com" in all_tasks
    assert "chase.com" in all_tasks
    assert "bankofamerica.com" in all_tasks
    assert "citimortgage.com" in all_tasks


def test_collect_reo_deduplicates_same_property_across_sources(monkeypatch):
    """Same address returned by two sources → only one record in output."""
    monkeypatch.setenv("REO_ENABLED", "true")
    monkeypatch.setenv("REO_BROWSER_USE_MAX_TASKS", "6")
    # Both HomePath and HomeSteps "find" the same property
    portal_text = "123 Main St, Burien, WA 98146\nProperty ID: WF-111\nParcel: 100000-0001"
    with patch("realtorfarm.collectors.reo.scrape_url", return_value=""), \
         patch("realtorfarm.collectors.reo.run_task", return_value=portal_text):
        records, candidates = collect_reo(city="Burien", lookback_days=1)
    addresses = [r["property_address"] for r in records]
    assert addresses.count("123 Main St, Burien, WA 98146") == 1


def test_collect_reo_skips_failed_source_and_continues(monkeypatch):
    """A source raising RuntimeError is skipped; other sources still run."""
    monkeypatch.setenv("REO_ENABLED", "true")
    monkeypatch.setenv("REO_BROWSER_USE_MAX_TASKS", "6")
    portal_text = "456 Oak Ave, Burien, WA 98146\nProperty ID: HP-222\nParcel: 200000-0002"
    side_effects = [
        RuntimeError("Browser Use failed"),  # HomePath fails
        portal_text,                          # HomeSteps succeeds
        RuntimeError("timed out"),            # Wells Fargo fails
        "",                                   # Chase empty
        "",                                   # BofA empty
        "",                                   # Citi empty
    ]
    with patch("realtorfarm.collectors.reo.scrape_url", return_value=""), \
         patch("realtorfarm.collectors.reo.run_task", side_effect=side_effects):
        records, candidates = collect_reo(city="Burien", lookback_days=1)
    assert isinstance(records, list)
    assert isinstance(candidates, list)
    # HomeSteps result must be present
    assert any("456 Oak Ave" in r["property_address"] for r in records)


def test_collect_reo_sends_missing_parcel_to_candidates(monkeypatch):
    """HUD listing with address but no parcel goes to candidates list."""
    monkeypatch.setenv("REO_ENABLED", "true")
    monkeypatch.setenv("REO_BROWSER_USE_MAX_TASKS", "0")
    # Return HUD_MISSING_PARCEL for the first zip, empty for the rest
    side_effects = [HUD_MISSING_PARCEL, "", "", ""]
    with patch("realtorfarm.collectors.reo.scrape_url", side_effect=side_effects):
        records, candidates = collect_reo(city="Burien", lookback_days=1)
    assert records == []
    assert len(candidates) == 1
    assert candidates[0]["rejection_reason"] == "missing_parcel_id"
    assert "152nd" in candidates[0]["property_address"]
