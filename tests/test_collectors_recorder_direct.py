"""Tests for recorder_direct.py — mocks SeleniumBase sb_cdp and Playwright to avoid real network calls."""
import re
import pytest
from unittest.mock import MagicMock, patch
from realtorfarm.collectors.recorder_direct import (
    collect_recorder_direct,
    _parse_rows,
    _parse_date,
)
from datetime import date


# ── _parse_date unit tests ────────────────────────────────────────────────────

def test_parse_date_mdyyyy():
    assert _parse_date("5/26/2026") == "2026-05-26"

def test_parse_date_iso():
    assert _parse_date("2026-05-26") == "2026-05-26"

def test_parse_date_padded():
    assert _parse_date("05/06/2026") == "2026-05-06"


# ── _parse_rows unit tests ────────────────────────────────────────────────────

SAMPLE_ROW = {
    "recording_number": "20260520001234",
    "doc_type": "NTS",
    "recorded_date": "5/20/2026",
    "grantor": "SMITH JOHN A",
    "grantee": "QUALITY LOAN SERVICE",
}


def test_parse_rows_returns_candidates():
    _, candidates = _parse_rows(
        [SAMPLE_ROW],
        signal="NOTS",
        city_variants={"kent"},
        start_date=date(2026, 5, 19),
    )
    assert len(candidates) == 1
    c = candidates[0]
    assert c["case_id"] == "20260520001234"
    assert c["signals"] == ["NOTS"]
    assert c["rejection_reason"] == "missing_parcel_id"
    assert c["recorded_date"] == "2026-05-20"
    assert "SMITH JOHN A" in c["notes"]


def test_parse_rows_returns_empty_records():
    records, _ = _parse_rows(
        [SAMPLE_ROW],
        signal="NOTS",
        city_variants={"kent"},
        start_date=date(2026, 5, 19),
    )
    assert records == []


def test_parse_rows_empty_input():
    records, candidates = _parse_rows(
        [],
        signal="NOTS",
        city_variants={"kent"},
        start_date=date(2026, 5, 19),
    )
    assert records == [] and candidates == []


# ── collect_recorder_direct integration tests ─────────────────────────────────

def test_collect_disabled_returns_empty(monkeypatch):
    monkeypatch.delenv("RECORDER_DIRECT_ENABLED", raising=False)
    r, c = collect_recorder_direct(city="Kent", lookback_days=1)
    assert r == [] and c == []


def _make_sb_mock(endpoint="ws://localhost:9222"):
    sb = MagicMock()
    sb.get_endpoint_url.return_value = endpoint
    sb.sleep.return_value = None
    sb.solve_captcha.return_value = None
    sb.wait_for_element_absent.return_value = None
    sb.quit.return_value = None
    return sb


def _make_tr_mock(row: dict) -> MagicMock:
    """Build a mock <tr> element with the given cell texts."""
    cells = [
        row.get("recording_number", ""),
        row.get("doc_type", ""),
        row.get("recorded_date", ""),
        row.get("grantor", ""),
        row.get("grantee", ""),
    ]
    cell_mocks = []
    for text in cells:
        td = MagicMock()
        td.inner_text.return_value = text
        cell_mocks.append(td)

    tr = MagicMock()
    tr.query_selector_all.return_value = cell_mocks
    return tr


def test_collect_enabled_returns_candidates(monkeypatch):
    monkeypatch.setenv("RECORDER_DIRECT_ENABLED", "true")

    with patch("realtorfarm.collectors.recorder_direct.sb_cdp") as mock_sb_cdp, \
         patch("realtorfarm.collectors.recorder_direct.sync_playwright") as mock_pw:

        mock_sb_cdp.Chrome.return_value = _make_sb_mock()

        # Build playwright mock chain
        tr = _make_tr_mock(SAMPLE_ROW)
        page = MagicMock()
        page.goto.return_value = None
        page.wait_for_load_state.return_value = None
        page.evaluate.return_value = None
        page.click.return_value = None
        page.query_selector_all.return_value = [tr]

        context = MagicMock()
        context.pages = [page]
        browser = MagicMock()
        browser.contexts = [context]
        pw_instance = MagicMock()
        pw_instance.chromium.connect_over_cdp.return_value = browser
        mock_pw.return_value.__enter__.return_value = pw_instance
        mock_pw.return_value.__exit__ = MagicMock(return_value=False)

        records, candidates = collect_recorder_direct(city="Kent", lookback_days=7)

    assert records == []  # Landmark never returns records directly
    assert len(candidates) >= 1
    assert candidates[0]["case_id"] == "20260520001234"
    assert candidates[0]["signals"] == ["NOTS"]


def test_collect_doctype_failure_is_caught(monkeypatch):
    """If a doc-type search throws, it's caught and the pipeline continues."""
    monkeypatch.setenv("RECORDER_DIRECT_ENABLED", "true")

    with patch("realtorfarm.collectors.recorder_direct.sb_cdp") as mock_sb_cdp:
        mock_sb_cdp.Chrome.side_effect = Exception("Chrome launch failed")
        records, candidates = collect_recorder_direct(city="Kent", lookback_days=1)

    # Should not raise — exceptions are caught internally
    assert records == []


# ── _parse_date edge-case tests ───────────────────────────────────────────────

def test_parse_date_empty_string():
    result = _parse_date("")
    assert result == date.today().isoformat()


def test_parse_date_timestamp_format():
    # Landmark sometimes appends time — regex extracts date portion, ignores time suffix
    result = _parse_date("5/20/2026 3:42 PM")
    assert result == "2026-05-20"


def test_parse_date_garbage():
    result = _parse_date("NOT A DATE")
    assert result == date.today().isoformat()
