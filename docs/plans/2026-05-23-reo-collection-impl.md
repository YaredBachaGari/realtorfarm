# REO Collection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add systematic REO (bank-owned property) collection via HUD Home Store (Firecrawl) and lender portals (Browser Use), gated behind `REO_ENABLED`.

**Architecture:** Single `reo.py` collector with one function per source; internal dedup by `(address.lower(), signal)`; registered in `collectors/__init__.py` with the same dual-guard pattern used by `recorder_direct` and `courts`.

**Tech Stack:** Python 3.11, Firecrawl REST (`scrape_url`), Browser Use Cloud (`run_task`), pytest + monkeypatch/unittest.mock

---

### Task 1: `reo.py` + 7 tests (TDD)

**Files:**
- Create: `src/realtorfarm/collectors/reo.py`
- Create: `tests/test_collectors_reo.py`

---

**Step 1: Write all 7 failing tests**

Create `tests/test_collectors_reo.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_collectors_reo.py -v
```

Expected: 7 failures — `ImportError: cannot import name 'collect_reo' from 'realtorfarm.collectors.reo'`

---

**Step 3: Implement `src/realtorfarm/collectors/reo.py`**

```python
"""Collect REO (bank-owned) properties from HUD Home Store and lender portals."""
from __future__ import annotations

import os
import re

from .browser_use import run_task
from .firecrawl import scrape_url

# City → zip code mapping for King County target cities
_CITY_ZIPS: dict[str, list[str]] = {
    "burien":  ["98146", "98148", "98166", "98168"],
    "kent":    ["98030", "98031", "98032", "98042"],
    "tukwila": ["98168", "98188"],
}

_PARCEL_RE = re.compile(r"\b([0-9]{6}-[0-9]{4}(?:-[0-9]{2})?)\b")
_PRICE_RE  = re.compile(r"\$\s*([0-9]{1,3}(?:,\d{3})*(?:\.\d{2})?)")
_ADDRESS_RE = re.compile(
    r"(\d{1,6}\s+[^\n.;]{2,80}?\b(?:Ave|St|Rd|Dr|Ln|Ct|Pl|Way|Blvd)\b[^\n]{0,60}WA\s+\d{5})",
    re.I,
)

_HUD_URL = "https://www.hudhomestore.gov/Listing/PropList.aspx?sState=WA&sZip={zip}"

# (source_key, starting_url, display_name)
_BROWSER_SOURCES: list[tuple[str, str, str]] = [
    ("homepath",    "https://www.homepath.com/",                              "Fannie Mae HomePath"),
    ("homesteps",   "https://www.homesteps.com/",                             "Freddie Mac HomeSteps"),
    ("wellsfargo",  "https://reo.wellsfargo.com/",                            "Wells Fargo REO"),
    ("chase",       "https://www.chase.com/mortgage/real-estate-owned",       "Chase REO"),
    ("bofa",        "https://realestate.bankofamerica.com/reo",               "Bank of America REO"),
    ("citi",        "https://www.citimortgage.com/mortgage/real-estate-owned","Citi REO"),
]


def collect_reo(
    *, city: str, lookback_days: int = 1
) -> tuple[list[dict[str, str]], list[dict]]:
    """Return REO canonical records and candidates for *city*.

    *lookback_days* is accepted for interface consistency but not used —
    REO portals show current inventory, not a dated feed.
    """
    if os.environ.get("REO_ENABLED", "").lower() != "true":
        return [], []

    zips = _CITY_ZIPS.get(city.lower(), [])
    records: list[dict[str, str]] = []
    candidates: list[dict] = []

    # HUD Home Store — one Firecrawl call per zip
    hud_r, hud_c = _collect_hud(city=city, zips=zips)
    records.extend(hud_r)
    candidates.extend(hud_c)

    # Lender portals — Browser Use, capped by REO_BROWSER_USE_MAX_TASKS
    max_tasks = int(os.environ.get("REO_BROWSER_USE_MAX_TASKS", "6"))
    tasks_run = 0
    for _key, url, source_name in _BROWSER_SOURCES:
        if tasks_run >= max_tasks:
            break
        try:
            r, c = _collect_browser_source(city=city, url=url, source_name=source_name)
            records.extend(r)
            candidates.extend(c)
        except (RuntimeError, TimeoutError, OSError, ValueError) as exc:
            print(f"[reo] {source_name} task failed for {city}: {exc}")
        tasks_run += 1

    records, candidates = _deduplicate(records, candidates)
    return records, candidates


# ── Source collectors ─────────────────────────────────────────────────────────

def _collect_hud(*, city: str, zips: list[str]) -> tuple[list[dict[str, str]], list[dict]]:
    records: list[dict[str, str]] = []
    candidates: list[dict] = []
    for zip_code in zips:
        url = _HUD_URL.format(zip=zip_code)
        try:
            text = scrape_url(url)
            if not text.strip():
                print(f"[reo] no HUD listings for zip {zip_code}")
                continue
            r, c = _parse_hud_text(text, city=city, source_url=url)
            records.extend(r)
            candidates.extend(c)
        except (RuntimeError, TimeoutError, OSError, ValueError) as exc:
            print(f"[reo] HUD zip {zip_code} failed: {exc}")
    return records, candidates


def _collect_browser_source(
    *, city: str, url: str, source_name: str
) -> tuple[list[dict[str, str]], list[dict]]:
    task = (
        f"Go to {url} and search for REO / bank-owned properties in {city}, WA. "
        f"Return each listing as: address, property ID or loan number if shown. "
        f"One property per line."
    )
    text = run_task(task)
    if not text.strip():
        print(f"[reo] no listings found for {source_name} in {city}")
        return [], []
    return _parse_portal_text(text, city=city, source_name=source_name, source_url=url)


# ── Parsers ───────────────────────────────────────────────────────────────────

def _parse_hud_text(
    text: str, *, city: str, source_url: str
) -> tuple[list[dict[str, str]], list[dict]]:
    """Parse Firecrawl markdown from HUD Home Store into records/candidates."""
    records: list[dict[str, str]] = []
    candidates: list[dict] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        block = block.strip()
        if not block:
            continue
        address  = _extract_address(block, city=city)
        parcel_id = _extract_parcel(block)
        case_id  = _extract_case_id(block)
        price    = _extract_price(block)
        notes    = f"List price: ${price}" if price else ""

        if parcel_id and address:
            records.append({
                "owner":            "HUD",
                "property_address": address,
                "parcel_id":        parcel_id,
                "signal":           "REO",
                "source":           "HUD Home Store",
                "source_url":       source_url,
                "recorded_date":    "",
                "case_id":          case_id,
                "notes":            notes,
            })
        elif address or case_id:
            candidates.append({
                "property_address": address,
                "parcel_id":        parcel_id,
                "case_id":          case_id,
                "signals":          ["REO"],
                "rejection_reason": "missing_parcel_id",
                "source_url":       source_url,
                "recorded_date":    "",
            })
    return records, candidates


def _parse_portal_text(
    text: str, *, city: str, source_name: str, source_url: str
) -> tuple[list[dict[str, str]], list[dict]]:
    """Parse Browser Use output from a lender portal into records/candidates."""
    records: list[dict[str, str]] = []
    candidates: list[dict] = []
    blocks = re.split(r"\n\s*\n", text.strip()) or [text.strip()]
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        address  = _extract_address(block, city=city)
        parcel_id = _extract_parcel(block)
        case_id  = _extract_case_id(block)
        price    = _extract_price(block)
        notes    = f"List price: ${price}" if price else ""

        if parcel_id and address:
            records.append({
                "owner":            source_name,
                "property_address": address,
                "parcel_id":        parcel_id,
                "signal":           "REO",
                "source":           source_name,
                "source_url":       source_url,
                "recorded_date":    "",
                "case_id":          case_id,
                "notes":            notes,
            })
        elif address or case_id:
            candidates.append({
                "property_address": address,
                "parcel_id":        parcel_id,
                "case_id":          case_id,
                "signals":          ["REO"],
                "rejection_reason": "missing_parcel_id",
                "source_url":       source_url,
                "recorded_date":    "",
            })
    return records, candidates


# ── Deduplication ─────────────────────────────────────────────────────────────

def _deduplicate(
    records: list[dict[str, str]],
    candidates: list[dict],
) -> tuple[list[dict[str, str]], list[dict]]:
    """Remove duplicate (address, signal) pairs; first source URL wins."""
    seen: set[tuple[str, str]] = set()
    deduped_records: list[dict[str, str]] = []
    for r in records:
        key = (r["property_address"].lower(), r["signal"])
        if key not in seen:
            seen.add(key)
            deduped_records.append(r)

    deduped_candidates: list[dict] = []
    for c in candidates:
        key = (c.get("property_address", "").lower(), "REO")
        if key not in seen:
            seen.add(key)
            deduped_candidates.append(c)

    return deduped_records, deduped_candidates


# ── Extraction helpers ────────────────────────────────────────────────────────

def _extract_parcel(text: str) -> str:
    m = _PARCEL_RE.search(text)
    return m.group(1) if m else ""


def _extract_address(text: str, *, city: str) -> str:
    city_re = re.compile(
        rf"(\d{{1,6}}\s+[^\n.;]{{2,80}}?\b{re.escape(city)}\b[^\n]{{0,30}}WA\s+\d{{5}}(?:-\d{{4}})?)",
        re.I,
    )
    m = city_re.search(text)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    m = _ADDRESS_RE.search(text)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _extract_case_id(text: str) -> str:
    """Extract HUD case numbers, state-prefixed IDs, or MLS IDs."""
    m = re.search(r"\b(\d{3}-\d{6,})\b", text)           # HUD: 251-123456
    if m:
        return m.group(1)
    m = re.search(r"\b([A-Z]{2}-\d{6,})\b", text)         # State-prefixed: WA-123456
    if m:
        return m.group(1)
    m = re.search(r"\b(MLS[:#\s]*\d{5,})\b", text, re.I)  # MLS: MLS#12345
    if m:
        return m.group(1)
    return ""


def _extract_price(text: str) -> str:
    m = _PRICE_RE.search(text)
    return m.group(1) if m else ""
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_collectors_reo.py -v
```

Expected: 7 PASSED

**Step 5: Run full suite to check no regressions**

```bash
pytest --tb=short -q
```

Expected: all existing tests still pass (73 + 7 = 80 total)

**Step 6: Commit**

```bash
git add src/realtorfarm/collectors/reo.py tests/test_collectors_reo.py
git commit -m "feat: add REO collector with HUD/HomePath/HomeSteps/bank portals"
```

---

### Task 2: Wire REO into `__init__.py` + `daily.yml` + 1 integration test

**Files:**
- Modify: `src/realtorfarm/collectors/__init__.py`
- Modify: `tests/test_collect_daily.py` (add 1 test at end of file)
- Modify: `.github/workflows/daily.yml`

---

**Step 1: Write the failing integration test**

Add this test at the bottom of `tests/test_collect_daily.py`:

```python
def test_collect_for_city_calls_reo_when_enabled(monkeypatch):
    monkeypatch.setenv("REO_ENABLED", "true")
    monkeypatch.setenv("REO_BROWSER_USE_MAX_TASKS", "0")  # Firecrawl only
    monkeypatch.setenv("BROWSER_USE_MAX_ENRICHMENTS", "0")
    with patch("realtorfarm.collectors.reo.scrape_url", return_value="") as mock_scrape, \
         patch("realtorfarm.collectors.legal_notices.scrape_url", return_value=""), \
         patch("realtorfarm.collectors.treasury.scrape_url", return_value=""):
        from realtorfarm.collectors import collect_for_city
        records, candidates = collect_for_city(city="Burien", lookback_days=1)
    # 4 HUD zip calls for Burien
    assert mock_scrape.call_count == 4
    assert isinstance(records, list)
```

**Step 2: Run the new test to verify it fails**

```bash
pytest tests/test_collect_daily.py::test_collect_for_city_calls_reo_when_enabled -v
```

Expected: FAILED — `ImportError` or the mock not being called (REO not registered yet)

**Step 3: Register REO in `src/realtorfarm/collectors/__init__.py`**

Add the import and guard block. The final file should look like this (add the two highlighted blocks):

```python
from __future__ import annotations

import os

from .courts import collect_courts
from .legal_notices import collect_legal_notices
from .recorder_direct import collect_recorder_direct
from .reo import collect_reo                          # ← ADD THIS IMPORT
from .treasury import collect_treasury


def collect_for_city(city: str, lookback_days: int = 1) -> tuple[list[dict[str, str]], list[dict]]:
    records: list[dict[str, str]] = []
    candidates: list[dict] = []

    notice_records, notice_candidates = collect_legal_notices(city=city, lookback_days=lookback_days)
    records.extend(notice_records)
    candidates.extend(notice_candidates)

    treasury_records = collect_treasury(city=city)
    records.extend(treasury_records)

    # Outer guard skips Browser Use quota when flag is off.
    # collect_recorder_direct also self-guards for callers outside collect_for_city.
    if os.environ.get("RECORDER_DIRECT_ENABLED", "").lower() == "true":
        rec_records, rec_candidates = collect_recorder_direct(city=city, lookback_days=lookback_days)
        records.extend(rec_records)
        candidates.extend(rec_candidates)

    # Same dual-guard pattern as recorder_direct above.
    if os.environ.get("COURTS_ENABLED", "").lower() == "true":
        court_records, court_candidates = collect_courts(city=city, lookback_days=lookback_days)
        records.extend(court_records)
        candidates.extend(court_candidates)

    # REO portals: HUD (Firecrawl) + lender portals (Browser Use).           ← ADD THIS BLOCK
    if os.environ.get("REO_ENABLED", "").lower() == "true":
        reo_records, reo_candidates = collect_reo(city=city, lookback_days=lookback_days)
        records.extend(reo_records)
        candidates.extend(reo_candidates)

    return records, candidates
```

**Step 4: Run the integration test to verify it passes**

```bash
pytest tests/test_collect_daily.py::test_collect_for_city_calls_reo_when_enabled -v
```

Expected: PASSED

**Step 5: Add env vars to `.github/workflows/daily.yml`**

In the `Collect records` step's `env:` block, add two lines after the existing `COURTS_ENABLED` line:

```yaml
          REO_ENABLED: ${{ vars.REO_ENABLED || 'false' }}
          REO_BROWSER_USE_MAX_TASKS: ${{ vars.REO_BROWSER_USE_MAX_TASKS || '6' }}
```

The full `env:` block should read:

```yaml
        env:
          FIRECRAWL_API_KEY: ${{ secrets.FIRECRAWL_API_KEY }}
          BROWSER_USE_API_KEY: ${{ secrets.BROWSER_USE_API_KEY }}
          BROWSER_USE_MAX_ENRICHMENTS: ${{ vars.BROWSER_USE_MAX_ENRICHMENTS || '10' }}
          RECORDER_DIRECT_ENABLED: ${{ vars.RECORDER_DIRECT_ENABLED || 'false' }}
          COURTS_ENABLED: ${{ vars.COURTS_ENABLED || 'false' }}
          REO_ENABLED: ${{ vars.REO_ENABLED || 'false' }}
          REO_BROWSER_USE_MAX_TASKS: ${{ vars.REO_BROWSER_USE_MAX_TASKS || '6' }}
```

**Step 6: Run the full test suite**

```bash
pytest --tb=short -q
```

Expected: all tests pass (80 + 1 = 81 total)

**Step 7: Commit**

```bash
git add src/realtorfarm/collectors/__init__.py \
        tests/test_collect_daily.py \
        .github/workflows/daily.yml
git commit -m "feat: register REO collector and add REO_ENABLED workflow env vars"
```
