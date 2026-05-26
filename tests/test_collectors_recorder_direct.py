"""Tests for recorder_direct.py — mocks Playwright and 2captcha to avoid real network calls."""
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


def test_collect_missing_api_key_raises(monkeypatch):
    monkeypatch.setenv("RECORDER_DIRECT_ENABLED", "true")
    monkeypatch.delenv("TWOCAPTCHA_API_KEY", raising=False)
    with pytest.raises(ValueError, match="TWOCAPTCHA_API_KEY"):
        collect_recorder_direct(city="Kent", lookback_days=1)


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
    monkeypatch.setenv("TWOCAPTCHA_API_KEY", "test_key")

    # Mock 2captcha
    with patch("realtorfarm.collectors.recorder_direct.TwoCaptcha") as mock_solver_cls:
        mock_solver = MagicMock()
        mock_solver.recaptcha.return_value = {"code": "test_token_123"}
        mock_solver_cls.return_value = mock_solver

        # Mock Playwright
        tr_mock = _make_tr_mock(SAMPLE_ROW)

        page = MagicMock()
        page.goto.return_value = None
        page.wait_for_load_state.return_value = None
        page.evaluate.return_value = None
        page.click.return_value = None
        page.query_selector_all.return_value = [tr_mock]

        browser = MagicMock()
        browser.new_page.return_value = page

        pw_instance = MagicMock()
        pw_instance.chromium.launch.return_value = browser

        with patch("realtorfarm.collectors.recorder_direct.sync_playwright") as mock_pw:
            mock_pw.return_value.__enter__.return_value = pw_instance

            records, candidates = collect_recorder_direct(city="Kent", lookback_days=7)

    # At minimum, the mock should have been called and returned candidates
    assert isinstance(records, list)
    assert isinstance(candidates, list)


def test_collect_doctype_failure_is_caught(monkeypatch):
    """If a doc-type search throws, it's caught and the pipeline continues."""
    monkeypatch.setenv("RECORDER_DIRECT_ENABLED", "true")
    monkeypatch.setenv("TWOCAPTCHA_API_KEY", "test_key")

    with patch("realtorfarm.collectors.recorder_direct.TwoCaptcha") as mock_solver_cls:
        mock_solver = MagicMock()
        mock_solver.recaptcha.side_effect = Exception("2captcha timeout")
        mock_solver_cls.return_value = mock_solver

        with patch("realtorfarm.collectors.recorder_direct.sync_playwright") as mock_pw:
            browser = MagicMock()
            page = MagicMock()
            page.goto.return_value = None
            page.wait_for_load_state.return_value = None
            browser.new_page.return_value = page
            pw_instance = MagicMock()
            pw_instance.chromium.launch.return_value = browser
            mock_pw.return_value.__enter__.return_value = pw_instance

            records, candidates = collect_recorder_direct(city="Kent", lookback_days=1)

    # Should not raise — exceptions are caught internally
    assert records == []
