# Bankruptcy Collection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add systematic bankruptcy collection from CourtListener (Western District of WA) for Chapter 7, 11, and 13 filings, gated behind `BANKRUPTCY_ENABLED`.

**Architecture:** Two new files — `courtlistener.py` (thin REST wrapper) and `bankruptcy.py` (collector). All results enter the candidates pipeline (no parcel number in bankruptcy filings → downstream parcel enrichment handles them). Registered in `collectors/__init__.py` with the same dual-guard pattern as REO and Courts.

**Tech Stack:** Python 3.11, `requests`, CourtListener REST API v3, pytest + monkeypatch/unittest.mock

---

### Task 1: `courtlistener.py` REST wrapper

**Files:**
- Create: `src/realtorfarm/collectors/courtlistener.py`

No unit tests for this file — it's a thin wrapper like `firecrawl.py`, and all bankruptcy tests mock its functions directly.

---

**Step 1: Create `src/realtorfarm/collectors/courtlistener.py`**

```python
"""CourtListener REST API wrapper — searches federal court dockets and party records."""
from __future__ import annotations

import os

import requests

COURTLISTENER_BASE = "https://www.courtlistener.com/api/rest/v3"


def search_dockets(
    *,
    court: str,
    chapter: int,
    date_filed_gte: str,
    date_filed_lte: str,
    api_key: str | None = None,
    page_size: int = 100,
) -> list[dict]:
    """Return all dockets matching court/chapter/date range.

    Follows CourtListener pagination via ``next`` links automatically.
    Returns a flat list of docket dicts with keys: id, docket_number, case_name, date_filed.
    """
    key = api_key or os.environ.get("COURTLISTENER_API_KEY", "")
    if not key:
        raise ValueError("COURTLISTENER_API_KEY is required")

    headers = {"Authorization": f"Token {key}"}
    params: dict = {
        "court": court,
        "chapter": chapter,
        "date_filed__gte": date_filed_gte,
        "date_filed__lte": date_filed_lte,
        "fields": "id,docket_number,case_name,date_filed",
        "page_size": page_size,
    }

    results: list[dict] = []
    url: str | None = f"{COURTLISTENER_BASE}/dockets/"
    while url:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("results", []))
        url = data.get("next")
        params = {}  # next URL already encodes all query params

    return results


def get_parties(
    *,
    docket_id: int,
    api_key: str | None = None,
) -> list[dict]:
    """Return party records for a docket.

    Each dict has keys: name, contact_information, party_types.
    contact_information is a list of address dicts (address1, city, state, zip_code).
    party_types is a list of role dicts (name: "Debtor" | "Joint Debtor" | ...).
    """
    key = api_key or os.environ.get("COURTLISTENER_API_KEY", "")
    if not key:
        raise ValueError("COURTLISTENER_API_KEY is required")

    headers = {"Authorization": f"Token {key}"}
    params = {
        "docket": docket_id,
        "fields": "name,contact_information,party_types",
    }

    resp = requests.get(
        f"{COURTLISTENER_BASE}/parties/",
        headers=headers,
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])
```

**Step 2: Verify the file is importable**

```bash
cd D:\projects\realtorfarm\.claude\worktrees\nice-bartik-6dcf3f
python -c "from realtorfarm.collectors.courtlistener import search_dockets, get_parties; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add src/realtorfarm/collectors/courtlistener.py
git commit -m "feat: add CourtListener REST wrapper for dockets and parties"
```

---

### Task 2: `bankruptcy.py` + 7 tests (TDD)

**Files:**
- Create: `src/realtorfarm/collectors/bankruptcy.py`
- Create: `tests/test_collectors_bankruptcy.py`

---

**Step 1: Write all 7 failing tests**

Create `tests/test_collectors_bankruptcy.py`:

```python
"""Tests for the Bankruptcy collector."""
import os
from unittest.mock import patch

from realtorfarm.collectors.bankruptcy import collect_bankruptcy


# ── Fixtures ─────────────────────────────────────────────────────────────────

BURIEN_DOCKET = {
    "id": 12345678,
    "docket_number": "2:26-bk-00123",
    "case_name": "In re Jane Smith",
    "date_filed": "2026-05-20",
}

BURIEN_PARTIES = [
    {
        "name": "Jane Smith",
        "party_types": [{"name": "Debtor"}],
        "contact_information": [{
            "address1": "12345 6th Ave SW",
            "city": "Burien",
            "state": "WA",
            "zip_code": "98146",
        }],
    }
]

OUT_OF_AREA_PARTIES = [
    {
        "name": "John Doe",
        "party_types": [{"name": "Debtor"}],
        "contact_information": [{
            "address1": "999 Far Away St",
            "city": "Seattle",
            "state": "WA",
            "zip_code": "98101",  # not a Burien zip
        }],
    }
]

NO_ADDRESS_PARTIES = [
    {
        "name": "Bob Builder",
        "party_types": [{"name": "Debtor"}],
        "contact_information": [],  # no address data in CourtListener
    }
]


# ── Tests ────────────────────────────────────────────────────────────────────

def test_collect_bankruptcy_returns_empty_when_disabled():
    """BANKRUPTCY_ENABLED not set → returns ([], []) immediately."""
    assert os.environ.get("BANKRUPTCY_ENABLED", "") != "true"
    records, candidates = collect_bankruptcy(city="Burien", lookback_days=1)
    assert records == []
    assert candidates == []


def test_search_dockets_calls_courtlistener_once_per_chapter(monkeypatch):
    """collect_bankruptcy issues one search_dockets call per chapter (7, 11, 13)."""
    monkeypatch.setenv("BANKRUPTCY_ENABLED", "true")
    with patch("realtorfarm.collectors.bankruptcy.search_dockets", return_value=[]) as mock_search, \
         patch("realtorfarm.collectors.bankruptcy.time") as mock_time:
        mock_time.sleep = lambda _: None
        collect_bankruptcy(city="Burien", lookback_days=1)
    assert mock_search.call_count == 3
    chapters_searched = {c.kwargs["chapter"] for c in mock_search.call_args_list}
    assert chapters_searched == {7, 11, 13}


def test_parse_debtor_address_filters_to_target_city_zip(monkeypatch):
    """Debtor ZIP in Burien → candidate kept; out-of-area ZIP → discarded."""
    monkeypatch.setenv("BANKRUPTCY_ENABLED", "true")
    out_of_area_docket = {**BURIEN_DOCKET, "id": 99999, "docket_number": "2:26-bk-99999"}
    with patch("realtorfarm.collectors.bankruptcy.search_dockets",
               side_effect=[[BURIEN_DOCKET], [out_of_area_docket], []]), \
         patch("realtorfarm.collectors.bankruptcy.get_parties",
               side_effect=[BURIEN_PARTIES, OUT_OF_AREA_PARTIES]), \
         patch("realtorfarm.collectors.bankruptcy.time") as mock_time:
        mock_time.sleep = lambda _: None
        records, candidates = collect_bankruptcy(city="Burien", lookback_days=1)
    assert len(candidates) == 1
    assert "98146" in candidates[0]["property_address"]


def test_collect_bankruptcy_produces_candidate_with_missing_parcel(monkeypatch):
    """In-city debtor address → candidate with rejection_reason='missing_parcel_id'."""
    monkeypatch.setenv("BANKRUPTCY_ENABLED", "true")
    with patch("realtorfarm.collectors.bankruptcy.search_dockets",
               side_effect=[[BURIEN_DOCKET], [], []]), \
         patch("realtorfarm.collectors.bankruptcy.get_parties", return_value=BURIEN_PARTIES), \
         patch("realtorfarm.collectors.bankruptcy.time") as mock_time:
        mock_time.sleep = lambda _: None
        records, candidates = collect_bankruptcy(city="Burien", lookback_days=1)
    assert records == []
    assert len(candidates) == 1
    c = candidates[0]
    assert c["rejection_reason"] == "missing_parcel_id"
    assert c["case_id"] == "2:26-bk-00123"
    assert c["signals"] == ["Bankruptcy"]
    assert "Burien" in c["property_address"]
    assert "Chapter 7" in c["notes"]


def test_collect_bankruptcy_deduplicates_same_case_across_chapters(monkeypatch):
    """Same docket_number returned by multiple chapter queries → one candidate."""
    monkeypatch.setenv("BANKRUPTCY_ENABLED", "true")
    # All 3 chapter queries return the same docket
    with patch("realtorfarm.collectors.bankruptcy.search_dockets", return_value=[BURIEN_DOCKET]), \
         patch("realtorfarm.collectors.bankruptcy.get_parties", return_value=BURIEN_PARTIES), \
         patch("realtorfarm.collectors.bankruptcy.time") as mock_time:
        mock_time.sleep = lambda _: None
        records, candidates = collect_bankruptcy(city="Burien", lookback_days=1)
    case_ids = [c["case_id"] for c in candidates]
    assert case_ids.count("2:26-bk-00123") == 1


def test_collect_bankruptcy_skips_failed_chapter_and_continues(monkeypatch):
    """Chapter 7 raises RuntimeError → Chapters 11 and 13 still run; no crash."""
    monkeypatch.setenv("BANKRUPTCY_ENABLED", "true")
    search_side_effects = [
        RuntimeError("API timeout"),   # Chapter 7 fails
        [BURIEN_DOCKET],               # Chapter 11 succeeds
        [],                            # Chapter 13 empty
    ]
    with patch("realtorfarm.collectors.bankruptcy.search_dockets",
               side_effect=search_side_effects), \
         patch("realtorfarm.collectors.bankruptcy.get_parties", return_value=BURIEN_PARTIES), \
         patch("realtorfarm.collectors.bankruptcy.time") as mock_time:
        mock_time.sleep = lambda _: None
        records, candidates = collect_bankruptcy(city="Burien", lookback_days=1)
    assert isinstance(records, list)
    assert isinstance(candidates, list)
    assert any(c["case_id"] == "2:26-bk-00123" for c in candidates)


def test_collect_bankruptcy_sends_no_address_case_to_candidates(monkeypatch):
    """Case with no debtor address → candidate with rejection_reason='missing_debtor_address'."""
    monkeypatch.setenv("BANKRUPTCY_ENABLED", "true")
    with patch("realtorfarm.collectors.bankruptcy.search_dockets",
               side_effect=[[BURIEN_DOCKET], [], []]), \
         patch("realtorfarm.collectors.bankruptcy.get_parties", return_value=NO_ADDRESS_PARTIES), \
         patch("realtorfarm.collectors.bankruptcy.time") as mock_time:
        mock_time.sleep = lambda _: None
        records, candidates = collect_bankruptcy(city="Burien", lookback_days=1)
    assert len(candidates) == 1
    assert candidates[0]["rejection_reason"] == "missing_debtor_address"
    assert candidates[0]["case_id"] == "2:26-bk-00123"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_collectors_bankruptcy.py -v
```

Expected: 7 failures — `ImportError: cannot import name 'collect_bankruptcy'`

**Step 3: Create `src/realtorfarm/collectors/bankruptcy.py`**

```python
"""Collect Bankruptcy signals from CourtListener (U.S. Bankruptcy Court, Western District WA)."""
from __future__ import annotations

import os
import re
import time
from datetime import date, timedelta

from .courtlistener import get_parties, search_dockets

_COURT = "wawb"  # Western District of Washington bankruptcy court
_CHAPTERS = [7, 11, 13]
_MIN_LOOKBACK = 7  # CourtListener indexing lag up to 48h; 7 days ensures full coverage
_RATE_SLEEP = 0.35  # stay under 3 req/sec CourtListener free-tier limit

_COURTLISTENER_BASE = "https://www.courtlistener.com"

# City → zip code mapping (same cities as other collectors)
_CITY_ZIPS: dict[str, list[str]] = {
    "burien":  ["98146", "98148", "98166", "98168"],
    "kent":    ["98030", "98031", "98032", "98042"],
    "tukwila": ["98168", "98188"],
}


def collect_bankruptcy(
    *, city: str, lookback_days: int = 1
) -> tuple[list[dict[str, str]], list[dict]]:
    """Return bankruptcy candidates for *city* from CourtListener WAWB dockets.

    All results are candidates (bankruptcy filings never include a parcel number).
    *lookback_days* is promoted to _MIN_LOOKBACK if smaller, to account for indexing lag.
    """
    if os.environ.get("BANKRUPTCY_ENABLED", "").lower() != "true":
        return [], []

    effective_lookback = max(lookback_days, _MIN_LOOKBACK)
    end_date = date.today()
    start_date = end_date - timedelta(days=effective_lookback)
    target_zips = set(_CITY_ZIPS.get(city.lower(), []))

    records: list[dict[str, str]] = []
    candidates: list[dict] = []

    for chapter in _CHAPTERS:
        try:
            _, c = _collect_chapter(
                chapter=chapter,
                city=city,
                target_zips=target_zips,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
            )
            candidates.extend(c)
        except (RuntimeError, TimeoutError, OSError, ValueError) as exc:
            print(f"[bankruptcy] Chapter {chapter} task failed for {city}: {exc}")

    candidates = _deduplicate(candidates)
    return records, candidates


# ── Chapter collector ─────────────────────────────────────────────────────────

def _collect_chapter(
    *,
    chapter: int,
    city: str,
    target_zips: set[str],
    start_date: str,
    end_date: str,
) -> tuple[list, list]:
    dockets = search_dockets(
        court=_COURT,
        chapter=chapter,
        date_filed_gte=start_date,
        date_filed_lte=end_date,
    )
    if not dockets:
        print(f"[bankruptcy] no Chapter {chapter} filings found in {_COURT}")
        return [], []

    candidates = []
    for docket in dockets:
        time.sleep(_RATE_SLEEP)
        candidate = _process_docket(
            docket=docket, chapter=chapter, target_zips=target_zips
        )
        if candidate is not None:
            candidates.append(candidate)

    if not candidates:
        print(f"[bankruptcy] no Chapter {chapter} filings matched {city}")

    return [], candidates


# ── Docket processor ──────────────────────────────────────────────────────────

def _process_docket(
    *, docket: dict, chapter: int, target_zips: set[str]
) -> dict | None:
    """Return a candidate dict for this docket, or None if outside target cities."""
    docket_id = docket["id"]
    docket_number = docket.get("docket_number", "")
    case_name = docket.get("case_name", "")
    date_filed = docket.get("date_filed", date.today().isoformat())
    source_url = f"{_COURTLISTENER_BASE}/docket/{docket_id}/"
    debtor_name = re.sub(r"(?i)^in\s+re\s+", "", case_name).strip()

    parties = get_parties(docket_id=docket_id)
    debtor = _find_debtor_party(parties)

    if debtor:
        address, zip_code = _extract_debtor_address(debtor)
        if zip_code and zip_code in target_zips:
            return {
                "property_address": address,
                "parcel_id":        "",
                "case_id":          docket_number,
                "signals":          ["Bankruptcy"],
                "rejection_reason": "missing_parcel_id",
                "source_url":       source_url,
                "recorded_date":    date_filed,
                "notes":            f"Chapter {chapter} bankruptcy; debtor: {debtor_name}",
            }
        elif zip_code:
            # Has an address but it's outside our target cities — skip
            return None

    # No address available (or debtor party not found)
    return {
        "property_address": "",
        "parcel_id":        "",
        "case_id":          docket_number,
        "signals":          ["Bankruptcy"],
        "rejection_reason": "missing_debtor_address",
        "source_url":       source_url,
        "recorded_date":    date_filed,
        "notes":            f"Chapter {chapter} bankruptcy; debtor: {debtor_name}",
    }


# ── Party helpers ─────────────────────────────────────────────────────────────

def _find_debtor_party(parties: list[dict]) -> dict | None:
    """Return the first Debtor or Joint Debtor party, or None."""
    debtor_roles = {"Debtor", "Joint Debtor"}
    for party in parties:
        for pt in party.get("party_types", []):
            if pt.get("name") in debtor_roles:
                return party
    return None


def _extract_debtor_address(party: dict) -> tuple[str, str]:
    """Return (formatted_address, zip_code) from a CourtListener party dict."""
    contacts = party.get("contact_information", [])
    if not contacts:
        return "", ""

    contact = contacts[0]
    address1 = contact.get("address1", "").strip()
    city_val  = contact.get("city", "").strip()
    state     = contact.get("state", "").strip()
    zip_code  = contact.get("zip_code", "").strip()[:5]  # first 5 digits (ignore ZIP+4)

    if not zip_code:
        return "", ""
    if not (address1 and city_val):
        return "", zip_code

    address = f"{address1}, {city_val}, {state} {zip_code}".strip()
    return address, zip_code


# ── Deduplication ─────────────────────────────────────────────────────────────

def _deduplicate(candidates: list[dict]) -> list[dict]:
    """Remove duplicate candidates by case_id. Keeps first occurrence."""
    seen: set[str] = set()
    deduped: list[dict] = []
    for c in candidates:
        key = c.get("case_id", "")
        if key and key not in seen:
            seen.add(key)
            deduped.append(c)
        elif not key:
            deduped.append(c)  # no case_id → keep all (shouldn't happen in practice)
    return deduped
```

**Step 4: Run the 7 new tests**

```bash
pytest tests/test_collectors_bankruptcy.py -v
```

All 7 must pass. If any fail, fix `bankruptcy.py` (not the tests) and re-run.

**Step 5: Run the full suite**

```bash
pytest --tb=short -q
```

Expected: all existing tests still pass (81 + 7 = 88 total).

**Step 6: Commit**

```bash
git add src/realtorfarm/collectors/bankruptcy.py tests/test_collectors_bankruptcy.py
git commit -m "feat: add Bankruptcy collector via CourtListener REST API (Chapter 7/11/13)"
```

---

### Task 3: Wire into `__init__.py` + `signals.json` + `daily.yml` + 1 integration test

**Files:**
- Modify: `src/realtorfarm/collectors/__init__.py`
- Modify: `config/signals.json`
- Modify: `tests/test_collect_daily.py` (add 1 test at end)
- Modify: `.github/workflows/daily.yml`

---

**Step 1: Write the failing integration test**

Add this test at the bottom of `tests/test_collect_daily.py`:

```python
def test_collect_for_city_calls_bankruptcy_when_enabled(monkeypatch):
    monkeypatch.setenv("BANKRUPTCY_ENABLED", "true")
    monkeypatch.setenv("BROWSER_USE_MAX_ENRICHMENTS", "0")
    with patch("realtorfarm.collectors.bankruptcy.search_dockets", return_value=[]) as mock_search, \
         patch("realtorfarm.collectors.legal_notices.scrape_url", return_value=""), \
         patch("realtorfarm.collectors.treasury.scrape_url", return_value=""), \
         patch("realtorfarm.collectors.bankruptcy.time") as mock_time:
        mock_time.sleep = lambda _: None
        from realtorfarm.collectors import collect_for_city
        records, candidates = collect_for_city(city="Burien", lookback_days=1)
    assert mock_search.call_count == 3  # one per chapter (7, 11, 13)
    assert isinstance(records, list)
```

**Step 2: Verify the test fails**

```bash
pytest tests/test_collect_daily.py::test_collect_for_city_calls_bankruptcy_when_enabled -v
```

Expected: FAIL — `bankruptcy` not registered in `collect_for_city` yet.

**Step 3: Register in `src/realtorfarm/collectors/__init__.py`**

Read the file first. Add the import and guard block. The final imports section must be:

```python
from .bankruptcy import collect_bankruptcy
from .courts import collect_courts
from .legal_notices import collect_legal_notices
from .recorder_direct import collect_recorder_direct
from .reo import collect_reo
from .treasury import collect_treasury
```

Add this block at the end of `collect_for_city`, after the `REO_ENABLED` block:

```python
    # Bankruptcy: CourtListener federal court filings (Chapter 7, 11, 13).
    if os.environ.get("BANKRUPTCY_ENABLED", "").lower() == "true":
        bk_records, bk_candidates = collect_bankruptcy(city=city, lookback_days=lookback_days)
        records.extend(bk_records)
        candidates.extend(bk_candidates)
```

**Step 4: Update `config/signals.json`**

Read the file first. Add `"chapter 11"` to the `Bankruptcy` aliases list:

```json
"Bankruptcy": ["bankruptcy schedules", "chapter 7", "chapter 11", "chapter 13"]
```

**Step 5: Add env vars to `.github/workflows/daily.yml`**

Read the file first. In the `Collect records` step's `env:` block, add after `REO_BROWSER_USE_MAX_TASKS`:

```yaml
          BANKRUPTCY_ENABLED: ${{ vars.BANKRUPTCY_ENABLED || 'false' }}
          COURTLISTENER_API_KEY: ${{ secrets.COURTLISTENER_API_KEY }}
```

The full `env:` block order must be:
1. `FIRECRAWL_API_KEY`
2. `BROWSER_USE_API_KEY`
3. `BROWSER_USE_MAX_ENRICHMENTS`
4. `RECORDER_DIRECT_ENABLED`
5. `COURTS_ENABLED`
6. `REO_ENABLED`
7. `REO_BROWSER_USE_MAX_TASKS`
8. `BANKRUPTCY_ENABLED`
9. `COURTLISTENER_API_KEY`

**Step 6: Verify the integration test passes**

```bash
pytest tests/test_collect_daily.py::test_collect_for_city_calls_bankruptcy_when_enabled -v
```

Expected: PASS.

**Step 7: Run the full suite**

```bash
pytest --tb=short -q
```

Expected: 89 tests pass (81 existing + 7 bankruptcy + 1 integration).

**Step 8: Commit**

```bash
git add src/realtorfarm/collectors/__init__.py \
        config/signals.json \
        tests/test_collect_daily.py \
        .github/workflows/daily.yml
git commit -m "feat: register Bankruptcy collector, add chapter 11 signal, update workflow"
```
