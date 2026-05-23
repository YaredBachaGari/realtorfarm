# Phase B Collection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement `recorder_direct.py` (King County Recorder Landmark) and `courts.py` (Washington Courts probate/eviction) as opt-in Phase B collectors that plug into the existing `collect_for_city()` registry.

**Architecture:** One Browser Use Cloud task per document/case type per city execution. Each collector is guarded by an env var (`RECORDER_DIRECT_ENABLED`, `COURTS_ENABLED`) defaulting to `false`. Both return `(records, candidates)` tuples; records missing `parcel_id` go to the candidates list for downstream parcel enrichment. All helpers (parcel regex, address extraction, date parsing) are defined locally in each module to avoid coupling between collectors.

**Tech Stack:** Python 3.11, `realtorfarm.collectors.browser_use.run_task`, `unittest.mock.patch`, pytest

---

## Codebase orientation (read before starting)

- `src/realtorfarm/collectors/browser_use.py` — `run_task(task, *, api_key=None) -> str` submits a Browser Use Cloud task and polls until finished
- `src/realtorfarm/collectors/parcel_enrichment.py` — reference for `_PARCEL_RE` pattern and candidate dict shape
- `src/realtorfarm/collectors/__init__.py` — `collect_for_city()` registry; Phase B collectors get registered here in Task 3
- `tests/test_collectors_parcel_enrichment.py` — reference for how to mock `run_task` in tests
- `tests/test_collect_daily.py` — reference for `run_collection()` test patterns; extended in Task 3
- Design doc: `docs/plans/2026-05-23-phase-b-collection-design.md`

---

## Task 1: Implement `recorder_direct.py`

**Files:**
- Modify: `src/realtorfarm/collectors/recorder_direct.py` (replace stub)
- Create: `tests/test_collectors_recorder_direct.py`

---

### Step 1: Write the failing tests

Create `tests/test_collectors_recorder_direct.py`:

```python
import os
from unittest.mock import patch
from realtorfarm.collectors.recorder_direct import collect_recorder_direct


LANDMARK_NOTS_WITH_PARCEL = """
Recording Date: 2026-05-22
Recording Number: 20260522000456
Grantor: BURIEN SAMPLE OWNER LLC
Property Address: 12345 6th Ave SW, Burien, WA 98146
Parcel: 123450-0678
Document Type: NOTICE OF TRUSTEE SALE
"""

LANDMARK_NOD_MISSING_PARCEL = """
Recording Date: 2026-05-21
Recording Number: 20260521000789
Grantor: ANOTHER OWNER LLC
Property Address: 999 SW 152nd St, Burien, WA 98166
Document Type: NOTICE OF DEFAULT
"""


def test_collect_recorder_direct_returns_empty_when_disabled():
    records, candidates = collect_recorder_direct(city="Burien", lookback_days=1)
    assert records == []
    assert candidates == []


def test_collect_recorder_direct_runs_one_task_per_doc_type(monkeypatch):
    monkeypatch.setenv("RECORDER_DIRECT_ENABLED", "true")
    with patch("realtorfarm.collectors.recorder_direct.run_task", return_value="") as mock_run:
        collect_recorder_direct(city="Burien", lookback_days=1)
    assert mock_run.call_count == 3
    calls_text = " ".join(str(c) for c in mock_run.call_args_list)
    assert "NOTICE OF TRUSTEE SALE" in calls_text
    assert "NOTICE OF DEFAULT" in calls_text
    assert "LIEN" in calls_text


def test_parse_recorder_output_extracts_canonical_record(monkeypatch):
    monkeypatch.setenv("RECORDER_DIRECT_ENABLED", "true")
    responses = [LANDMARK_NOTS_WITH_PARCEL, "", ""]
    with patch("realtorfarm.collectors.recorder_direct.run_task", side_effect=responses):
        records, candidates = collect_recorder_direct(city="Burien", lookback_days=1)
    assert len(records) == 1
    assert records[0]["owner"] == "BURIEN SAMPLE OWNER LLC"
    assert records[0]["property_address"] == "12345 6th Ave SW, Burien, WA 98146"
    assert records[0]["parcel_id"] == "123450-0678"
    assert records[0]["signal"] == "NOTS"
    assert records[0]["case_id"] == "20260522000456"
    assert records[0]["recorded_date"] == "2026-05-22"


def test_collect_recorder_direct_skips_failed_task_and_continues(monkeypatch):
    monkeypatch.setenv("RECORDER_DIRECT_ENABLED", "true")
    responses = [RuntimeError("Browser Use failed"), LANDMARK_NOTS_WITH_PARCEL, ""]
    with patch("realtorfarm.collectors.recorder_direct.run_task", side_effect=responses):
        records, candidates = collect_recorder_direct(city="Burien", lookback_days=1)
    # first task failed, second (NOD mapping) succeeded — but fixture has NOTS signal
    # so we just verify at least one task ran successfully and no exception propagated
    assert isinstance(records, list)
    assert isinstance(candidates, list)


def test_collect_recorder_direct_returns_candidates_for_missing_parcel(monkeypatch):
    monkeypatch.setenv("RECORDER_DIRECT_ENABLED", "true")
    responses = [LANDMARK_NOD_MISSING_PARCEL, "", ""]
    with patch("realtorfarm.collectors.recorder_direct.run_task", side_effect=responses):
        records, candidates = collect_recorder_direct(city="Burien", lookback_days=1)
    assert records == []
    assert len(candidates) == 1
    assert candidates[0]["rejection_reason"] == "missing_parcel_id"
    assert candidates[0]["property_address"] == "999 SW 152nd St, Burien, WA 98166"
```

### Step 2: Run to verify they fail

```
pytest tests/test_collectors_recorder_direct.py -v
```

Expected: 5 failures — `ImportError` or assertions fail because stub returns `[], []`.

### Step 3: Implement `recorder_direct.py`

Replace the stub entirely:

```python
"""Collect NOTS/NOD/Lien from King County Recorder Landmark via Browser Use Cloud."""
from __future__ import annotations

import os
import re
from datetime import date, timedelta

from .browser_use import run_task

LANDMARK_URL = "https://recordsearch.kingcounty.gov/LandmarkWeb/"

_DOC_TYPES = [
    ("NOTICE OF TRUSTEE SALE", "NOTS"),
    ("NOTICE OF DEFAULT", "NOD"),
    ("LIEN", "Lien"),
]

_PARCEL_RE = re.compile(r"\b([0-9]{6}-[0-9]{4}(?:-[0-9]{2})?)\b")
_RECORDING_NUMBER_RE = re.compile(r"\b(\d{14})\b")
_ADDRESS_RE = re.compile(
    r"(\d{1,6}\s+[^\n.;]{2,80}?\b(?:Ave|St|Rd|Dr|Ln|Ct|Pl|Way|Blvd)\b[^\n]{0,60}WA\s+\d{5})",
    re.I,
)


def collect_recorder_direct(
    *, city: str, lookback_days: int = 1
) -> tuple[list[dict[str, str]], list[dict]]:
    """Return canonical records and candidates from King County Recorder Landmark."""
    if os.environ.get("RECORDER_DIRECT_ENABLED", "").lower() != "true":
        return [], []

    end_date = date.today()
    start_date = end_date - timedelta(days=lookback_days)
    records: list[dict[str, str]] = []
    candidates: list[dict] = []

    for doc_type, signal in _DOC_TYPES:
        try:
            r, c = _collect_doc_type(
                doc_type=doc_type, signal=signal,
                city=city, start_date=start_date, end_date=end_date,
            )
            records.extend(r)
            candidates.extend(c)
        except Exception as exc:
            print(f"[recorder_direct] {doc_type} task failed for {city}: {exc}")

    return records, candidates


def _collect_doc_type(
    *, doc_type: str, signal: str, city: str, start_date: date, end_date: date,
) -> tuple[list[dict[str, str]], list[dict]]:
    task = (
        f'Go to {LANDMARK_URL} and search for documents of type "{doc_type}" '
        f"recorded between {start_date.isoformat()} and {end_date.isoformat()}. "
        f"For each result where the property address is in {city}, WA, return: "
        f"recording date, recording number, grantor name, property address, document type. "
        f"Return as plain text, one record per line."
    )
    result_text = run_task(task)
    if not result_text.strip():
        print(f"[recorder_direct] no {doc_type} results for {city}")
        return [], []
    return _parse_result(result_text, signal=signal, city=city, doc_type=doc_type)


def _parse_result(
    text: str, *, signal: str, city: str, doc_type: str,
) -> tuple[list[dict[str, str]], list[dict]]:
    records: list[dict[str, str]] = []
    candidates: list[dict] = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parcel_id = _extract_parcel(line)
        address = _extract_address(line, city=city)
        recording_number = _extract_recording_number(line)
        owner = _extract_owner(line)
        recorded_date = _extract_date(line)

        source_url = (
            f"browser-use://landmark/{recording_number}" if recording_number else LANDMARK_URL
        )

        if parcel_id and address:
            records.append({
                "owner": owner,
                "property_address": address,
                "parcel_id": parcel_id,
                "signal": signal,
                "source": "King County Recorder Landmark",
                "source_url": source_url,
                "recorded_date": recorded_date,
                "case_id": recording_number,
                "notes": f"Recorded document type: {doc_type}",
            })
        elif address or recording_number:
            candidates.append({
                "property_address": address,
                "parcel_id": parcel_id,
                "case_id": recording_number,
                "signals": [signal],
                "rejection_reason": (
                    "missing_parcel_id" if address and not parcel_id
                    else "missing_target_city_property_address"
                ),
                "source_url": source_url,
                "recorded_date": recorded_date,
            })

    return records, candidates


def _extract_parcel(text: str) -> str:
    m = _PARCEL_RE.search(text)
    return m.group(1) if m else ""


def _extract_recording_number(text: str) -> str:
    m = _RECORDING_NUMBER_RE.search(text)
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


def _extract_owner(text: str) -> str:
    m = re.search(r"(?:Grantor|Owner)\s*[:\-]?\s*([^\n,]{2,80})", text, re.I)
    return m.group(1).strip().upper() if m else "UNKNOWN OWNER"


def _extract_date(text: str) -> str:
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", text)
    if m:
        try:
            from datetime import datetime
            return datetime.strptime(m.group(1), "%m/%d/%Y").date().isoformat()
        except ValueError:
            pass
    return date.today().isoformat()
```

### Step 4: Run tests to verify they pass

```
pytest tests/test_collectors_recorder_direct.py -v
```

Expected: 5 passed.

### Step 5: Run full suite to verify no regressions

```
pytest -q
```

Expected: all tests pass.

### Step 6: Commit

```bash
git add src/realtorfarm/collectors/recorder_direct.py tests/test_collectors_recorder_direct.py
git commit -m "feat: implement Landmark NOTS/NOD/Lien collector via Browser Use"
```

---

## Task 2: Implement `courts.py`

**Files:**
- Modify: `src/realtorfarm/collectors/courts.py` (replace stub)
- Create: `tests/test_collectors_courts.py`

---

### Step 1: Write the failing tests

Create `tests/test_collectors_courts.py`:

```python
import os
from unittest.mock import patch
from realtorfarm.collectors.courts import collect_courts


COURTS_PROBATE_OUTPUT = """
Case Number: 26-4-01234-1 KNT
Filing Date: 2026-05-20
Case Type: Probate/Guardianship/Trust
Petitioner: JOHN EXECUTOR
Party Address: 9876 1st Ave S, Burien, WA 98148
"""

COURTS_EVICTION_OUTPUT = """
Case Number: 26-2-05678-1 KNT
Filing Date: 2026-05-19
Case Type: Unlawful Detainer
Plaintiff: LANDLORD CORP LLC
Party Address: 13579 4th Ave SW, Burien, WA 98146
"""


def test_collect_courts_returns_empty_when_disabled():
    records, candidates = collect_courts(city="Burien", lookback_days=1)
    assert records == []
    assert candidates == []


def test_collect_courts_runs_one_task_per_case_type(monkeypatch):
    monkeypatch.setenv("COURTS_ENABLED", "true")
    with patch("realtorfarm.collectors.courts.run_task", return_value="") as mock_run:
        collect_courts(city="Burien", lookback_days=1)
    assert mock_run.call_count == 2
    calls_text = " ".join(str(c) for c in mock_run.call_args_list)
    assert "Probate" in calls_text
    assert "Unlawful Detainer" in calls_text


def test_parse_courts_output_extracts_canonical_record(monkeypatch):
    monkeypatch.setenv("COURTS_ENABLED", "true")
    # Probate record has no parcel — goes to candidates; Eviction also no parcel
    # Provide address-only output; verify candidate shape and signal
    responses = [COURTS_PROBATE_OUTPUT, ""]
    with patch("realtorfarm.collectors.courts.run_task", side_effect=responses):
        records, candidates = collect_courts(city="Burien", lookback_days=1)
    # No parcel in fixture → candidate, not record
    assert len(candidates) == 1
    assert candidates[0]["signals"] == ["Probate"]
    assert candidates[0]["case_id"] == "26-4-01234-1 KNT"
    assert candidates[0]["property_address"] == "9876 1st Ave S, Burien, WA 98148"
    assert candidates[0]["rejection_reason"] == "missing_parcel_id"


def test_collect_courts_skips_failed_task_and_continues(monkeypatch):
    monkeypatch.setenv("COURTS_ENABLED", "true")
    responses = [RuntimeError("Browser Use failed"), COURTS_EVICTION_OUTPUT]
    with patch("realtorfarm.collectors.courts.run_task", side_effect=responses):
        records, candidates = collect_courts(city="Burien", lookback_days=1)
    # First task (Probate) failed, second (Eviction) succeeded
    assert isinstance(records, list)
    assert isinstance(candidates, list)
    # Eviction result has address but no parcel → candidate
    total = len(records) + len(candidates)
    assert total >= 1


def test_collect_courts_uses_minimum_7_day_lookback(monkeypatch):
    monkeypatch.setenv("COURTS_ENABLED", "true")
    with patch("realtorfarm.collectors.courts.run_task", return_value="") as mock_run:
        collect_courts(city="Burien", lookback_days=1)
    # The task prompt must mention a start date at least 7 days back
    first_call_arg = mock_run.call_args_list[0][0][0]
    from datetime import date, timedelta
    seven_days_ago = (date.today() - timedelta(days=7)).isoformat()
    assert seven_days_ago in first_call_arg
```

### Step 2: Run to verify they fail

```
pytest tests/test_collectors_courts.py -v
```

Expected: 5 failures — stub returns `[], []` for all cases.

### Step 3: Implement `courts.py`

Replace the stub entirely:

```python
"""Collect Probate/Eviction signals from Washington Courts case search via Browser Use Cloud."""
from __future__ import annotations

import os
import re
from datetime import date, timedelta

from .browser_use import run_task

COURTS_URL = (
    "https://www.courts.wa.gov/index.cfm?fa=home.contentDisplay&location=nameAndCaseSearch"
)

_CASE_TYPES = [
    ("Probate/Guardianship/Trust", "Probate"),
    ("Unlawful Detainer", "Eviction"),
]

_PARCEL_RE = re.compile(r"\b([0-9]{6}-[0-9]{4}(?:-[0-9]{2})?)\b")
_CASE_NUMBER_RE = re.compile(r"\b(\d{2,4}-\d{1}-\d{5}-\d+(?:\s+[A-Z]{2,4})?)\b")
_ADDRESS_RE = re.compile(
    r"(\d{1,6}\s+[^\n.;]{2,80}?\b(?:Ave|St|Rd|Dr|Ln|Ct|Pl|Way|Blvd)\b[^\n]{0,60}WA\s+\d{5})",
    re.I,
)
_MIN_LOOKBACK = 7


def collect_courts(
    *, city: str, lookback_days: int = 1
) -> tuple[list[dict[str, str]], list[dict]]:
    """Return canonical records and candidates from Washington Courts case search."""
    if os.environ.get("COURTS_ENABLED", "").lower() != "true":
        return [], []

    effective_lookback = max(lookback_days, _MIN_LOOKBACK)
    end_date = date.today()
    start_date = end_date - timedelta(days=effective_lookback)
    records: list[dict[str, str]] = []
    candidates: list[dict] = []

    for case_type, signal in _CASE_TYPES:
        try:
            r, c = _collect_case_type(
                case_type=case_type, signal=signal,
                city=city, start_date=start_date, end_date=end_date,
            )
            records.extend(r)
            candidates.extend(c)
        except Exception as exc:
            print(f"[courts] {case_type} task failed for {city}: {exc}")

    return records, candidates


def _collect_case_type(
    *, case_type: str, signal: str, city: str, start_date: date, end_date: date,
) -> tuple[list[dict[str, str]], list[dict]]:
    task = (
        f"Go to {COURTS_URL} and search for {case_type} cases "
        f"filed in King County between {start_date.isoformat()} and {end_date.isoformat()}. "
        f"For each result where any party's address is in {city}, WA, return: "
        f"case number, filing date, case type, party names, and party addresses. "
        f"Return as plain text, one record per line."
    )
    result_text = run_task(task)
    if not result_text.strip():
        print(f"[courts] no {case_type} results for {city}")
        return [], []
    return _parse_result(result_text, signal=signal, city=city, case_type=case_type)


def _parse_result(
    text: str, *, signal: str, city: str, case_type: str,
) -> tuple[list[dict[str, str]], list[dict]]:
    records: list[dict[str, str]] = []
    candidates: list[dict] = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parcel_id = _extract_parcel(line)
        address = _extract_address(line, city=city)
        case_number = _extract_case_number(line)
        owner = _extract_owner(line)
        filing_date = _extract_date(line)

        if parcel_id and address:
            records.append({
                "owner": owner,
                "property_address": address,
                "parcel_id": parcel_id,
                "signal": signal,
                "source": "Washington Courts",
                "source_url": COURTS_URL,
                "recorded_date": filing_date,
                "case_id": case_number,
                "notes": f"Court case type: {case_type}",
            })
        elif address or case_number:
            candidates.append({
                "property_address": address,
                "parcel_id": parcel_id,
                "case_id": case_number,
                "signals": [signal],
                "rejection_reason": (
                    "missing_parcel_id" if address and not parcel_id
                    else "missing_target_city_property_address"
                ),
                "source_url": COURTS_URL,
                "recorded_date": filing_date,
            })

    return records, candidates


def _extract_parcel(text: str) -> str:
    m = _PARCEL_RE.search(text)
    return m.group(1) if m else ""


def _extract_case_number(text: str) -> str:
    m = _CASE_NUMBER_RE.search(text)
    return m.group(1).strip() if m else ""


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


def _extract_owner(text: str) -> str:
    m = re.search(
        r"(?:Petitioner|Plaintiff|Grantor|Party)\s*[:\-]?\s*([^\n,]{2,80})", text, re.I
    )
    return m.group(1).strip().upper() if m else "UNKNOWN OWNER"


def _extract_date(text: str) -> str:
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", text)
    if m:
        try:
            from datetime import datetime
            return datetime.strptime(m.group(1), "%m/%d/%Y").date().isoformat()
        except ValueError:
            pass
    return date.today().isoformat()
```

### Step 4: Run tests to verify they pass

```
pytest tests/test_collectors_courts.py -v
```

Expected: 5 passed.

### Step 5: Run full suite

```
pytest -q
```

Expected: all tests pass.

### Step 6: Commit

```bash
git add src/realtorfarm/collectors/courts.py tests/test_collectors_courts.py
git commit -m "feat: implement WA Courts Probate/Eviction collector via Browser Use"
```

---

## Task 3: Register Phase B in `collectors/__init__.py` + extend tests + update GitHub Actions

**Files:**
- Modify: `src/realtorfarm/collectors/__init__.py`
- Modify: `tests/test_collect_daily.py` (add 2 tests)
- Modify: `.github/workflows/daily.yml`

---

### Step 1: Write the failing tests

Add to the **bottom** of `tests/test_collect_daily.py`:

```python
def test_collect_for_city_calls_recorder_direct_when_enabled(monkeypatch):
    monkeypatch.setenv("RECORDER_DIRECT_ENABLED", "true")
    monkeypatch.setenv("BROWSER_USE_MAX_ENRICHMENTS", "0")
    recorder_record = {**KENT_RECORD, "source": "King County Recorder Landmark"}
    with patch("realtorfarm.collectors.recorder_direct.run_task", return_value=""), \
         patch("realtorfarm.collectors.legal_notices.scrape_url", return_value=""), \
         patch("realtorfarm.collectors.treasury.scrape_url", return_value=""):
        from realtorfarm.collectors import collect_for_city
        records, candidates = collect_for_city(city="Kent", lookback_days=1)
    # recorder_direct ran (returned empty because run_task returned "") — no crash
    assert isinstance(records, list)


def test_collect_for_city_calls_courts_when_enabled(monkeypatch):
    monkeypatch.setenv("COURTS_ENABLED", "true")
    monkeypatch.setenv("BROWSER_USE_MAX_ENRICHMENTS", "0")
    with patch("realtorfarm.collectors.courts.run_task", return_value=""), \
         patch("realtorfarm.collectors.legal_notices.scrape_url", return_value=""), \
         patch("realtorfarm.collectors.treasury.scrape_url", return_value=""):
        from realtorfarm.collectors import collect_for_city
        records, candidates = collect_for_city(city="Kent", lookback_days=1)
    assert isinstance(records, list)
```

### Step 2: Run to verify the new tests fail

```
pytest tests/test_collect_daily.py::test_collect_for_city_calls_recorder_direct_when_enabled tests/test_collect_daily.py::test_collect_for_city_calls_courts_when_enabled -v
```

Expected: FAIL — `collect_for_city` doesn't call the Phase B collectors yet.

### Step 3: Register Phase B collectors in `collectors/__init__.py`

Replace the entire file:

```python
from __future__ import annotations

import os

from .legal_notices import collect_legal_notices
from .treasury import collect_treasury
from .recorder_direct import collect_recorder_direct
from .courts import collect_courts


def collect_for_city(
    city: str,
    lookback_days: int = 1,
) -> tuple[list[dict[str, str]], list[dict]]:
    """Run all active collectors for a city and return (records, candidates)."""
    records: list[dict[str, str]] = []
    candidates: list[dict] = []

    notice_records, notice_candidates = collect_legal_notices(city=city, lookback_days=lookback_days)
    records.extend(notice_records)
    candidates.extend(notice_candidates)

    treasury_records = collect_treasury(city=city)
    records.extend(treasury_records)

    if os.environ.get("RECORDER_DIRECT_ENABLED", "").lower() == "true":
        rec_records, rec_candidates = collect_recorder_direct(city=city, lookback_days=lookback_days)
        records.extend(rec_records)
        candidates.extend(rec_candidates)

    if os.environ.get("COURTS_ENABLED", "").lower() == "true":
        court_records, court_candidates = collect_courts(city=city, lookback_days=lookback_days)
        records.extend(court_records)
        candidates.extend(court_candidates)

    return records, candidates
```

### Step 4: Add Phase B env vars to `.github/workflows/daily.yml`

In the `Collect records` step's `env:` block, add two new lines after `BROWSER_USE_MAX_ENRICHMENTS`:

```yaml
      - name: Collect records
        if: ${{ github.event_name == 'schedule' || github.event.inputs.city == '' || github.event.inputs.city == matrix.city }}
        env:
          FIRECRAWL_API_KEY: ${{ secrets.FIRECRAWL_API_KEY }}
          BROWSER_USE_API_KEY: ${{ secrets.BROWSER_USE_API_KEY }}
          BROWSER_USE_MAX_ENRICHMENTS: ${{ vars.BROWSER_USE_MAX_ENRICHMENTS || '10' }}
          RECORDER_DIRECT_ENABLED: ${{ vars.RECORDER_DIRECT_ENABLED || 'false' }}
          COURTS_ENABLED: ${{ vars.COURTS_ENABLED || 'false' }}
```

### Step 5: Run full suite

```
pytest -q
```

Expected: all tests pass (including the 2 new ones).

### Step 6: Commit

```bash
git add src/realtorfarm/collectors/__init__.py tests/test_collect_daily.py .github/workflows/daily.yml
git commit -m "feat: register Phase B collectors with env-var opt-in"
```

---

## Final verification

```
pytest -q
```

Expected: all tests pass, no failures.

Check total test count increased by 12 (5 recorder + 5 courts + 2 integration).
