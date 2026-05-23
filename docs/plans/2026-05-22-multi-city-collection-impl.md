# Multi-City Automated Collection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Firecrawl + Browser Use collection layer that populates `data/cities/<city>/daily/merged.csv` for Burien, Kent, and Tukwila daily via GitHub Actions, feeding the existing deterministic score/report pipeline.

**Architecture:** Firecrawl scrapes public legal notice publications (NOTS/NOD/Liens) and the King County Treasury tax-delinquent page for all three cities. The existing `scrape_notice_sources_with_diagnostics()` extractor parses the text. Browser Use Cloud fills in missing parcel IDs or addresses for rejected candidates. `collect_daily.py` appends only net-new rows to `merged.csv` (no overwrites, dedup by parcel+signal+case+source). GitHub Actions runs the full collect→score→upload cycle on a cron (7 AM Pacific, Mon–Fri) with a matrix over the three cities.

**Tech Stack:** Python 3.10+, `requests` (Firecrawl REST API + Browser Use REST API), `pytest`, GitHub Actions, Vercel Blob (already wired in `run_daily.py`).

**Branch:** `feat/multi-city-collection` (already created)

**Env vars required locally:** Copy from `src/realtorfarm/.env.local` → project root `.env.local`, or export individually:
```
FIRECRAWL_API_KEY=fc-...
BROWSER_USE_API_KEY=bu_...
BLOB_READ_WRITE_TOKEN=vercel_blob_rw_...
BROWSER_USE_MAX_ENRICHMENTS=10   # default; set to 0 to skip enrichment in tests
```

---

## Task 1: Add dependencies and collectors package skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `src/realtorfarm/collectors/__init__.py`
- Create: `src/realtorfarm/collectors/firecrawl.py` (stub)
- Create: `src/realtorfarm/collectors/browser_use.py` (stub)
- Create: `src/realtorfarm/collectors/legal_notices.py` (stub)
- Create: `src/realtorfarm/collectors/treasury.py` (stub)
- Create: `src/realtorfarm/collectors/parcel_enrichment.py` (stub)
- Create: `src/realtorfarm/collectors/courts.py` (Phase B stub)
- Create: `src/realtorfarm/collectors/recorder_direct.py` (Phase B stub)

**Step 1: Add `requests` to project dependencies**

In `pyproject.toml`, change:
```toml
dependencies = []
```
to:
```toml
dependencies = ["requests>=2.31"]
```

**Step 2: Create the collectors package**

`src/realtorfarm/collectors/__init__.py`:
```python
from __future__ import annotations

from .legal_notices import collect_legal_notices
from .treasury import collect_treasury


def collect_for_city(
    city: str,
    lookback_days: int = 1,
) -> tuple[list[dict[str, str]], list[dict]]:
    """Run all Phase A+C collectors for a city and return (records, candidates)."""
    records: list[dict[str, str]] = []
    candidates: list[dict] = []

    notice_records, notice_candidates = collect_legal_notices(city=city, lookback_days=lookback_days)
    records.extend(notice_records)
    candidates.extend(notice_candidates)

    treasury_records = collect_treasury(city=city)
    records.extend(treasury_records)

    return records, candidates
```

**Step 3: Create stub files (will be implemented in subsequent tasks)**

`src/realtorfarm/collectors/firecrawl.py`:
```python
from __future__ import annotations
"""Firecrawl REST API wrapper — scrapes public web pages to markdown text."""

import os
import requests

FIRECRAWL_BASE = "https://api.firecrawl.dev/v1"


def scrape_url(url: str, *, api_key: str | None = None, timeout: int = 60) -> str:
    """Fetch a URL via Firecrawl and return its markdown text."""
    raise NotImplementedError
```

`src/realtorfarm/collectors/browser_use.py`:
```python
from __future__ import annotations
"""Browser Use Cloud REST API wrapper — runs browser tasks and returns result text."""

import os
import time
import requests

BROWSER_USE_BASE = "https://api.browser-use.com/api/v1"


def run_task(task: str, *, api_key: str | None = None, poll_interval: int = 5, timeout: int = 300) -> str:
    """Submit a Browser Use Cloud task and block until it finishes, returning the output text."""
    raise NotImplementedError
```

`src/realtorfarm/collectors/legal_notices.py`:
```python
from __future__ import annotations
"""Collect NOTS/NOD/Liens from public legal notice publications via Firecrawl."""


def collect_legal_notices(*, city: str, lookback_days: int = 1) -> tuple[list[dict], list[dict]]:
    """Return (accepted_records, rejected_candidates) for target city from legal notice pubs."""
    raise NotImplementedError
```

`src/realtorfarm/collectors/treasury.py`:
```python
from __future__ import annotations
"""Collect Tax Delinquent 3+ Years signal from King County Treasury page via Firecrawl."""


def collect_treasury(*, city: str) -> list[dict[str, str]]:
    """Return canonical records for tax-delinquent properties in target city."""
    raise NotImplementedError
```

`src/realtorfarm/collectors/parcel_enrichment.py`:
```python
from __future__ import annotations
"""Use Browser Use Cloud to fill missing parcel_id or property_address for rejected candidates."""


def enrich_candidates(
    candidates: list[dict],
    *,
    city: str,
    max_enrichments: int = 10,
) -> list[dict[str, str]]:
    """Return canonical records built from enriched candidates (address or parcel filled)."""
    raise NotImplementedError
```

`src/realtorfarm/collectors/courts.py`:
```python
from __future__ import annotations
"""Phase B stub: Washington Courts name/case search (probate, eviction, civil judgment).

When implemented, this collector will use Browser Use Cloud to query
https://www.courts.wa.gov/index.cfm?fa=home.contentDisplay&location=nameAndCaseSearch
for the target city, extract probate/eviction case records, and return canonical rows.

Register in collectors/__init__.py collect_for_city() when ready.
"""


def collect_courts(*, city: str, lookback_days: int = 1) -> tuple[list[dict], list[dict]]:
    """Phase B — not yet implemented."""
    return [], []
```

`src/realtorfarm/collectors/recorder_direct.py`:
```python
from __future__ import annotations
"""Phase B stub: King County Recorder Landmark direct access via Browser Use Cloud.

When implemented, this collector will use Browser Use Cloud to navigate Landmark
(https://kingcounty.gov/en/dept/executive-services/.../recorders-office/records-search),
search by document type + date range for NOTS/NOD/Liens, download each document's text,
and pass it to the existing scrape_notice_sources_with_diagnostics() extractor.

Use this collector when legal notice publications miss a filing (usually within 24–48 hrs
of recording before newspaper publication).

Register in collectors/__init__.py collect_for_city() when ready.
"""


def collect_recorder_direct(*, city: str, lookback_days: int = 1) -> tuple[list[dict], list[dict]]:
    """Phase B — not yet implemented."""
    return [], []
```

**Step 4: Install and verify package loads**

```bash
pip install -e ".[dev]"
python -c "from realtorfarm.collectors import collect_for_city; print('ok')"
```
Expected: `ok`

**Step 5: Run existing tests to confirm nothing broken**

```bash
pytest -q
```
Expected: all existing tests pass.

**Step 6: Commit**

```bash
git add pyproject.toml src/realtorfarm/collectors/
git commit -m "feat: add collectors package skeleton and Phase B stubs"
```

---

## Task 2: Implement Firecrawl wrapper

**Files:**
- Modify: `src/realtorfarm/collectors/firecrawl.py`
- Create: `tests/test_collectors_firecrawl.py`

**Step 1: Write the failing test**

`tests/test_collectors_firecrawl.py`:
```python
from unittest.mock import patch, MagicMock
from realtorfarm.collectors.firecrawl import scrape_url


MOCK_FIRECRAWL_RESPONSE = {
    "success": True,
    "data": {
        "markdown": "# Legal Notices\n\nNotice of Trustee's Sale...",
        "metadata": {"statusCode": 200},
    },
}


def test_scrape_url_returns_markdown_text():
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_FIRECRAWL_RESPONSE
    mock_resp.raise_for_status.return_value = None

    with patch("realtorfarm.collectors.firecrawl.requests.post", return_value=mock_resp) as mock_post:
        result = scrape_url("https://example.com/legals", api_key="fc-test")

    assert result == "# Legal Notices\n\nNotice of Trustee's Sale..."
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "https://api.firecrawl.dev/v1/scrape" in call_kwargs[0][0]
    assert call_kwargs[1]["json"]["url"] == "https://example.com/legals"


def test_scrape_url_reads_api_key_from_env(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-from-env")
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_FIRECRAWL_RESPONSE
    mock_resp.raise_for_status.return_value = None

    with patch("realtorfarm.collectors.firecrawl.requests.post", return_value=mock_resp) as mock_post:
        scrape_url("https://example.com/legals")

    headers = mock_post.call_args[1]["headers"]
    assert "fc-from-env" in headers["Authorization"]


def test_scrape_url_raises_on_missing_api_key(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    import pytest
    with pytest.raises(ValueError, match="FIRECRAWL_API_KEY"):
        scrape_url("https://example.com/legals")


def test_scrape_url_returns_empty_string_on_missing_markdown():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"success": True, "data": {}}
    mock_resp.raise_for_status.return_value = None

    with patch("realtorfarm.collectors.firecrawl.requests.post", return_value=mock_resp):
        result = scrape_url("https://example.com/legals", api_key="fc-test")

    assert result == ""
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_collectors_firecrawl.py -v
```
Expected: FAIL — `NotImplementedError`

**Step 3: Implement**

`src/realtorfarm/collectors/firecrawl.py`:
```python
from __future__ import annotations

import os
import requests

FIRECRAWL_BASE = "https://api.firecrawl.dev/v1"


def scrape_url(url: str, *, api_key: str | None = None, timeout: int = 60) -> str:
    """Fetch a URL via Firecrawl and return its markdown text."""
    key = api_key or os.environ.get("FIRECRAWL_API_KEY", "")
    if not key:
        raise ValueError("FIRECRAWL_API_KEY is required")
    response = requests.post(
        f"{FIRECRAWL_BASE}/scrape",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"url": url, "formats": ["markdown"]},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json().get("data", {}).get("markdown", "")
```

**Step 4: Run tests**

```bash
pytest tests/test_collectors_firecrawl.py -v
```
Expected: all 4 PASS

**Step 5: Commit**

```bash
git add src/realtorfarm/collectors/firecrawl.py tests/test_collectors_firecrawl.py
git commit -m "feat: implement Firecrawl REST wrapper"
```

---

## Task 3: Implement legal notices collector

**Files:**
- Modify: `src/realtorfarm/collectors/legal_notices.py`
- Create: `tests/test_collectors_legal_notices.py`

**Step 1: Write the failing tests**

`tests/test_collectors_legal_notices.py`:
```python
from unittest.mock import patch
from datetime import date
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


def test_collect_legal_notices_returns_records_for_kent(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")

    with patch("realtorfarm.collectors.legal_notices.scrape_url", return_value=KENT_NOTS_MARKDOWN):
        records, candidates = collect_legal_notices(city="Kent", lookback_days=30)

    assert any(r["signal"] == "NOTS" and "Kent" in r["property_address"] for r in records)


def test_collect_legal_notices_filters_to_target_city(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")

    with patch("realtorfarm.collectors.legal_notices.scrape_url", return_value=BURIEN_NOTS_MARKDOWN):
        records, _ = collect_legal_notices(city="Kent", lookback_days=30)

    assert records == [], "Burien notices must not appear in Kent results"


def test_collect_legal_notices_returns_candidates_for_enrichment(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
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
```

**Step 2: Run to verify failure**

```bash
pytest tests/test_collectors_legal_notices.py -v
```
Expected: FAIL — `NotImplementedError`

**Step 3: Implement**

`src/realtorfarm/collectors/legal_notices.py`:
```python
from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from realtorfarm.extractors.public_notices import scrape_notice_sources_with_diagnostics
from .firecrawl import scrape_url

LEGAL_NOTICE_SOURCES = [
    "https://www.southcountyjournal.com/classifieds/public-notices/",
    "https://www.djc.com/legal_notices/",
    "https://www.publicnoticeads.com/wa/search/?SearchString=&county=King&category=0",
]


def collect_legal_notices(
    *,
    city: str,
    lookback_days: int = 1,
) -> tuple[list[dict[str, str]], list[dict]]:
    """Scrape legal notice publications via Firecrawl and extract target-city distress records."""
    temp_files: list[Path] = []
    source_paths: list[str] = []

    for url in LEGAL_NOTICE_SOURCES:
        try:
            text = scrape_url(url)
        except Exception as exc:
            print(f"[legal_notices] firecrawl failed for {url}: {exc}")
            continue
        if not text.strip():
            continue
        tmp = tempfile.NamedTemporaryFile(
            suffix=".md", delete=False, mode="w", encoding="utf-8"
        )
        tmp.write(text)
        tmp.close()
        temp_files.append(Path(tmp.name))
        source_paths.append(tmp.name)

    if not source_paths:
        return [], []

    try:
        records, diagnostics = scrape_notice_sources_with_diagnostics(
            source_paths,
            accessed=date.today(),
            target_city=city,
        )
    finally:
        for f in temp_files:
            f.unlink(missing_ok=True)

    return records, diagnostics.get("candidates", [])
```

**Step 4: Run tests**

```bash
pytest tests/test_collectors_legal_notices.py -v
```
Expected: all 4 PASS

**Step 5: Full suite check**

```bash
pytest -q
```
Expected: all pass.

**Step 6: Commit**

```bash
git add src/realtorfarm/collectors/legal_notices.py tests/test_collectors_legal_notices.py
git commit -m "feat: implement legal notices collector via Firecrawl"
```

---

## Task 4: Implement Treasury collector

**Files:**
- Modify: `src/realtorfarm/collectors/treasury.py`
- Create: `tests/test_collectors_treasury.py`

**Step 1: Write the failing tests**

`tests/test_collectors_treasury.py`:
```python
from unittest.mock import patch
from realtorfarm.collectors.treasury import collect_treasury, TREASURY_URL


TREASURY_MARKDOWN = """
# King County Tax Foreclosure Properties

The following properties are subject to tax foreclosure:

| Parcel Number | Owner Name | Situs Address | Years Delinquent |
|---|---|---|---|
| 232204-9055 | KENT DELINQUENT OWNER LLC | 415 W Gowe St, Kent, WA 98032 | 4 |
| 123450-0999 | BURIEN DELINQUENT OWNER | 10001 15th Ave SW, Burien, WA 98146 | 3 |
| 004000-0200 | TUKWILA DELINQUENT OWNER | 14500 Interurban Ave S, Tukwila, WA 98168 | 5 |
| 000100-0001 | RENTON OWNER | 100 Main Ave S, Renton, WA 98057 | 3 |
"""


def test_collect_treasury_returns_kent_parcels_only():
    with patch("realtorfarm.collectors.treasury.scrape_url", return_value=TREASURY_MARKDOWN):
        records = collect_treasury(city="Kent")

    assert len(records) == 1
    assert records[0]["signal"] == "Tax Delinquent 3+ Years Free-and-Clear"
    assert "Kent" in records[0]["property_address"]
    assert records[0]["parcel_id"] == "232204-9055"
    assert records[0]["owner"] == "KENT DELINQUENT OWNER LLC"


def test_collect_treasury_excludes_other_cities():
    with patch("realtorfarm.collectors.treasury.scrape_url", return_value=TREASURY_MARKDOWN):
        records = collect_treasury(city="Kent")

    addresses = [r["property_address"] for r in records]
    assert not any("Renton" in a for a in addresses)
    assert not any("Burien" in a for a in addresses)


def test_collect_treasury_returns_burien_records():
    with patch("realtorfarm.collectors.treasury.scrape_url", return_value=TREASURY_MARKDOWN):
        records = collect_treasury(city="Burien")

    assert len(records) == 1
    assert "Burien" in records[0]["property_address"]


def test_collect_treasury_returns_empty_on_scrape_failure():
    with patch("realtorfarm.collectors.treasury.scrape_url", side_effect=Exception("timeout")):
        records = collect_treasury(city="Kent")

    assert records == []


def test_treasury_url_is_king_county_official():
    assert "kingcounty.gov" in TREASURY_URL
```

**Step 2: Run to verify failure**

```bash
pytest tests/test_collectors_treasury.py -v
```
Expected: FAIL — `NotImplementedError`

**Step 3: Implement**

`src/realtorfarm/collectors/treasury.py`:
```python
from __future__ import annotations

import re
from datetime import date

from .firecrawl import scrape_url

TREASURY_URL = (
    "https://kingcounty.gov/en/dept/executive-services/buildings-property/"
    "treasury-operations/tax-foreclosures"
)

_PARCEL_RE = re.compile(r"\b([0-9]{6}-[0-9]{4}(?:-[0-9]{2})?)\b")
_CITY_PATTERN = re.compile(
    r"\b(?:Burien|Kent|Tukwila)\b[^|\n]{0,60}WA\s+\d{5}", re.I
)


def collect_treasury(*, city: str) -> list[dict[str, str]]:
    """Return canonical Tax Delinquent rows for target city from King County Treasury page."""
    try:
        text = scrape_url(TREASURY_URL)
    except Exception as exc:
        print(f"[treasury] firecrawl failed: {exc}")
        return []

    return _parse_treasury_text(text, city=city)


def _parse_treasury_text(text: str, *, city: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    city_re = re.compile(
        rf"\b{re.escape(city)}\b[^|\n]{{0,60}}WA\s+\d{{5}}", re.I
    )

    for line in text.splitlines():
        if not city_re.search(line):
            continue
        parcel_match = _PARCEL_RE.search(line)
        if not parcel_match:
            continue
        parcel_id = parcel_match.group(1)
        address = _extract_address_from_line(line, city=city)
        owner = _extract_owner_from_line(line)
        records.append({
            "owner": owner,
            "property_address": address,
            "parcel_id": parcel_id,
            "signal": "Tax Delinquent 3+ Years Free-and-Clear",
            "source": "King County Treasury tax foreclosure",
            "source_url": TREASURY_URL,
            "recorded_date": date.today().isoformat(),
            "case_id": "",
            "notes": "Tax delinquent 3+ years per King County Treasury foreclosure list",
        })
    return records


def _extract_address_from_line(line: str, *, city: str) -> str:
    city_re = re.compile(
        rf"(\d{{1,6}}\s+[^|,]{{2,60}}?\b{re.escape(city)}\b[^|]{{0,30}}WA\s+\d{{5}}(?:-\d{{4}})?)",
        re.I,
    )
    m = city_re.search(line)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _extract_owner_from_line(line: str) -> str:
    # Markdown table rows: | parcel | owner | address | years |
    parts = [p.strip() for p in line.split("|") if p.strip()]
    if len(parts) >= 2:
        return parts[1].upper()
    return "UNKNOWN OWNER"
```

**Step 4: Run tests**

```bash
pytest tests/test_collectors_treasury.py -v
```
Expected: all 5 PASS

**Step 5: Commit**

```bash
git add src/realtorfarm/collectors/treasury.py tests/test_collectors_treasury.py
git commit -m "feat: implement Treasury tax-delinquent collector via Firecrawl"
```

---

## Task 5: Implement Browser Use Cloud wrapper

**Files:**
- Modify: `src/realtorfarm/collectors/browser_use.py`
- Create: `tests/test_collectors_browser_use.py`

**Step 1: Write the failing tests**

`tests/test_collectors_browser_use.py`:
```python
from unittest.mock import patch, MagicMock, call
from realtorfarm.collectors.browser_use import run_task


def _mock_response(data: dict) -> MagicMock:
    m = MagicMock()
    m.json.return_value = data
    m.raise_for_status.return_value = None
    return m


def test_run_task_returns_output_on_success():
    submit_resp = _mock_response({"id": "task_abc123"})
    poll_resp = _mock_response({"id": "task_abc123", "status": "finished", "output": "Parcel: 232204-9055\nAddress: 415 W Gowe St, Kent, WA 98032"})

    with patch("realtorfarm.collectors.browser_use.requests.post", return_value=submit_resp), \
         patch("realtorfarm.collectors.browser_use.requests.get", return_value=poll_resp):
        result = run_task("find parcel details", api_key="bu_test")

    assert "232204-9055" in result
    assert "Kent" in result


def test_run_task_polls_until_finished():
    submit_resp = _mock_response({"id": "task_xyz"})
    running_resp = _mock_response({"id": "task_xyz", "status": "running", "output": None})
    done_resp = _mock_response({"id": "task_xyz", "status": "finished", "output": "result text"})

    with patch("realtorfarm.collectors.browser_use.requests.post", return_value=submit_resp), \
         patch("realtorfarm.collectors.browser_use.requests.get", side_effect=[running_resp, done_resp]), \
         patch("realtorfarm.collectors.browser_use.time.sleep"):
        result = run_task("find parcel details", api_key="bu_test", poll_interval=1)

    assert result == "result text"


def test_run_task_raises_on_failure_status():
    import pytest
    submit_resp = _mock_response({"id": "task_fail"})
    fail_resp = _mock_response({"id": "task_fail", "status": "failed", "output": None})

    with patch("realtorfarm.collectors.browser_use.requests.post", return_value=submit_resp), \
         patch("realtorfarm.collectors.browser_use.requests.get", return_value=fail_resp):
        with pytest.raises(RuntimeError, match="failed"):
            run_task("find parcel details", api_key="bu_test")


def test_run_task_reads_api_key_from_env(monkeypatch):
    monkeypatch.setenv("BROWSER_USE_API_KEY", "bu_from_env")
    submit_resp = _mock_response({"id": "task_env"})
    done_resp = _mock_response({"id": "task_env", "status": "finished", "output": "ok"})

    with patch("realtorfarm.collectors.browser_use.requests.post", return_value=submit_resp) as mock_post, \
         patch("realtorfarm.collectors.browser_use.requests.get", return_value=done_resp):
        run_task("task")

    headers = mock_post.call_args[1]["headers"]
    assert "bu_from_env" in headers["Authorization"]


def test_run_task_raises_on_missing_api_key(monkeypatch):
    import pytest
    monkeypatch.delenv("BROWSER_USE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="BROWSER_USE_API_KEY"):
        run_task("task")
```

**Step 2: Run to verify failure**

```bash
pytest tests/test_collectors_browser_use.py -v
```
Expected: FAIL — `NotImplementedError`

**Step 3: Implement**

`src/realtorfarm/collectors/browser_use.py`:
```python
from __future__ import annotations

import os
import time
import requests

BROWSER_USE_BASE = "https://api.browser-use.com/api/v1"


def run_task(
    task: str,
    *,
    api_key: str | None = None,
    poll_interval: int = 5,
    timeout: int = 300,
) -> str:
    """Submit a Browser Use Cloud task and block until finished, returning output text."""
    key = api_key or os.environ.get("BROWSER_USE_API_KEY", "")
    if not key:
        raise ValueError("BROWSER_USE_API_KEY is required")

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    resp = requests.post(
        f"{BROWSER_USE_BASE}/run-task",
        headers=headers,
        json={"task": task},
        timeout=30,
    )
    resp.raise_for_status()
    task_id = resp.json()["id"]

    deadline = time.time() + timeout
    while time.time() < deadline:
        poll = requests.get(f"{BROWSER_USE_BASE}/task/{task_id}", headers=headers, timeout=30)
        poll.raise_for_status()
        data = poll.json()
        status = data.get("status", "")
        if status == "finished":
            return data.get("output", "") or ""
        if status == "failed":
            raise RuntimeError(f"Browser Use task {task_id} failed")
        time.sleep(poll_interval)

    raise TimeoutError(f"Browser Use task {task_id} did not finish in {timeout}s")
```

**Step 4: Run tests**

```bash
pytest tests/test_collectors_browser_use.py -v
```
Expected: all 5 PASS

**Step 5: Commit**

```bash
git add src/realtorfarm/collectors/browser_use.py tests/test_collectors_browser_use.py
git commit -m "feat: implement Browser Use Cloud REST wrapper"
```

---

## Task 6: Implement parcel enrichment

**Files:**
- Modify: `src/realtorfarm/collectors/parcel_enrichment.py`
- Create: `tests/test_collectors_parcel_enrichment.py`

**Step 1: Write the failing tests**

`tests/test_collectors_parcel_enrichment.py`:
```python
from unittest.mock import patch
from realtorfarm.collectors.parcel_enrichment import enrich_candidates


CANDIDATE_MISSING_PARCEL = {
    "source_url": "https://example.com/notice",
    "target_city": "Kent",
    "signals": ["NOTS"],
    "property_address": "310 W Meeker St, Kent, WA 98032",
    "parcel_id": "",
    "case_id": "KENT-2026-0100",
    "recorded_date": "2026-05-20",
    "rejection_reason": "missing_parcel_id",
    "enrichment_needed": True,
}

CANDIDATE_MISSING_ADDRESS = {
    "source_url": "https://example.com/notice2",
    "target_city": "Kent",
    "signals": ["NOTS"],
    "property_address": "",
    "parcel_id": "232204-9001",
    "case_id": "",
    "recorded_date": "2026-05-20",
    "rejection_reason": "missing_target_city_property_address",
    "enrichment_needed": True,
}

CANDIDATE_WRONG_REJECTION = {
    "source_url": "https://example.com/notice3",
    "target_city": "Kent",
    "signals": [],
    "property_address": "",
    "parcel_id": "",
    "case_id": "",
    "recorded_date": "2026-05-20",
    "rejection_reason": "missing_distress_signal",
    "enrichment_needed": True,
}

PARCEL_VIEWER_RESULT_WITH_PARCEL = "Parcel Account Number: 232204-9010\nSitus Address: 310 W Meeker St, Kent, WA 98032\nOwner: KENT TEST LLC"
PARCEL_VIEWER_RESULT_WITH_ADDRESS = "Situs Address: 220 4th Ave S, Kent, WA 98032\nParcel Account Number: 232204-9001\nOwner: KENT SAMPLE OWNER LLC"


def test_enrichment_fills_parcel_for_candidate_missing_parcel():
    with patch("realtorfarm.collectors.parcel_enrichment.run_task", return_value=PARCEL_VIEWER_RESULT_WITH_PARCEL):
        records = enrich_candidates([CANDIDATE_MISSING_PARCEL], city="Kent", max_enrichments=10)

    assert len(records) == 1
    assert records[0]["parcel_id"] != ""
    assert records[0]["signal"] == "NOTS"


def test_enrichment_fills_address_for_candidate_missing_address():
    with patch("realtorfarm.collectors.parcel_enrichment.run_task", return_value=PARCEL_VIEWER_RESULT_WITH_ADDRESS):
        records = enrich_candidates([CANDIDATE_MISSING_ADDRESS], city="Kent", max_enrichments=10)

    assert len(records) == 1
    assert "Kent" in records[0]["property_address"]
    assert records[0]["parcel_id"] == "232204-9001"


def test_enrichment_skips_wrong_rejection_reason():
    with patch("realtorfarm.collectors.parcel_enrichment.run_task") as mock_bu:
        records = enrich_candidates([CANDIDATE_WRONG_REJECTION], city="Kent", max_enrichments=10)

    mock_bu.assert_not_called()
    assert records == []


def test_enrichment_respects_max_cap():
    candidates = [CANDIDATE_MISSING_PARCEL] * 20

    with patch("realtorfarm.collectors.parcel_enrichment.run_task", return_value=PARCEL_VIEWER_RESULT_WITH_PARCEL) as mock_bu:
        enrich_candidates(candidates, city="Kent", max_enrichments=3)

    assert mock_bu.call_count == 3


def test_enrichment_returns_empty_on_zero_cap():
    with patch("realtorfarm.collectors.parcel_enrichment.run_task") as mock_bu:
        records = enrich_candidates([CANDIDATE_MISSING_PARCEL], city="Kent", max_enrichments=0)

    mock_bu.assert_not_called()
    assert records == []


def test_enrichment_skips_candidate_on_browser_use_failure():
    with patch("realtorfarm.collectors.parcel_enrichment.run_task", side_effect=Exception("timeout")):
        records = enrich_candidates([CANDIDATE_MISSING_PARCEL], city="Kent", max_enrichments=10)

    assert records == []
```

**Step 2: Run to verify failure**

```bash
pytest tests/test_collectors_parcel_enrichment.py -v
```
Expected: FAIL — `NotImplementedError`

**Step 3: Implement**

`src/realtorfarm/collectors/parcel_enrichment.py`:
```python
from __future__ import annotations

import re
from datetime import date

from .browser_use import run_task

PARCEL_VIEWER_URL = "https://blue.kingcounty.com/Assessor/eRealProperty/default.aspx"

_PARCEL_RE = re.compile(r"\b([0-9]{6}-[0-9]{4}(?:-[0-9]{2})?)\b")
_ADDRESS_RE = re.compile(
    r"(\d{1,6}\s+[^\n.;]{2,80}?\b(?:Ave|St|Rd|Dr|Ln|Ct|Pl|Way|Blvd)\b[^\n]{0,60}WA\s+\d{5})",
    re.I,
)

_ENRICHABLE = {"missing_parcel_id", "missing_target_city_property_address"}


def enrich_candidates(
    candidates: list[dict],
    *,
    city: str,
    max_enrichments: int = 10,
) -> list[dict[str, str]]:
    """Return canonical records built from Browser Use parcel enrichment of rejected candidates."""
    if max_enrichments == 0:
        return []

    records: list[dict[str, str]] = []
    count = 0

    for candidate in candidates:
        if count >= max_enrichments:
            break
        if candidate.get("rejection_reason") not in _ENRICHABLE:
            continue

        try:
            enriched = _enrich_one(candidate, city=city)
        except Exception as exc:
            print(f"[parcel_enrichment] Browser Use failed for {candidate.get('case_id', '?')}: {exc}")
            continue

        if enriched:
            records.append(enriched)
        count += 1

    return records


def _enrich_one(candidate: dict, *, city: str) -> dict[str, str] | None:
    parcel_id = candidate.get("parcel_id", "")
    address = candidate.get("property_address", "")

    if parcel_id and not address:
        task = (
            f"Go to {PARCEL_VIEWER_URL} and search for parcel number {parcel_id}. "
            f"Return the situs address, parcel account number, and owner name as plain text."
        )
    elif address and not parcel_id:
        task = (
            f"Go to {PARCEL_VIEWER_URL} and search for this address: {address}. "
            f"Return the parcel account number, situs address, and owner name as plain text."
        )
    else:
        return None

    result_text = run_task(task)
    if not result_text:
        return None

    filled_parcel = parcel_id or _extract_parcel(result_text)
    filled_address = address or _extract_address(result_text, city=city)

    if not filled_parcel or not filled_address:
        return None

    signals = candidate.get("signals", [])
    if not signals:
        return None

    return {
        "owner": _extract_owner(result_text),
        "property_address": filled_address,
        "parcel_id": filled_parcel,
        "signal": signals[0],
        "source": "public legal notice + parcel viewer enrichment",
        "source_url": candidate.get("source_url", ""),
        "recorded_date": candidate.get("recorded_date", date.today().isoformat()),
        "case_id": candidate.get("case_id", ""),
        "notes": "Address or parcel enriched via King County Parcel Viewer (Browser Use Cloud)",
    }


def _extract_parcel(text: str) -> str:
    m = _PARCEL_RE.search(text)
    return m.group(1) if m else ""


def _extract_address(text: str, *, city: str) -> str:
    city_pattern = re.compile(
        rf"(\d{{1,6}}\s+[^\n.;]{{2,80}}?\b{re.escape(city)}\b[^\n]{{0,30}}WA\s+\d{{5}}(?:-\d{{4}})?)",
        re.I,
    )
    m = city_pattern.search(text)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    m = _ADDRESS_RE.search(text)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _extract_owner(text: str) -> str:
    m = re.search(r"(?:Owner|Taxpayer)\s*[:\-]?\s*([^\n]+)", text, re.I)
    return m.group(1).strip().upper() if m else "UNKNOWN OWNER"
```

**Step 4: Run tests**

```bash
pytest tests/test_collectors_parcel_enrichment.py -v
```
Expected: all 6 PASS

**Step 5: Full suite**

```bash
pytest -q
```
Expected: all pass.

**Step 6: Commit**

```bash
git add src/realtorfarm/collectors/parcel_enrichment.py tests/test_collectors_parcel_enrichment.py
git commit -m "feat: implement parcel enrichment via Browser Use Cloud"
```

---

## Task 7: Implement collect_daily.py orchestrator

**Files:**
- Create: `scripts/collect_daily.py`
- Create: `tests/test_collect_daily.py`

**Step 1: Write the failing tests**

`tests/test_collect_daily.py`:
```python
import csv
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

KENT_RECORD = {
    "owner": "KENT TEST OWNER LLC",
    "property_address": "220 4th Ave S, Kent, WA 98032",
    "parcel_id": "232204-9001",
    "signal": "NOTS",
    "source": "public legal notice",
    "source_url": "https://example.com/notice",
    "recorded_date": "2026-05-20",
    "case_id": "KENT-2026-0099",
    "notes": "Extracted from public legal notice text",
}


def _write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = ["owner", "property_address", "parcel_id", "signal", "source",
                  "source_url", "recorded_date", "case_id", "notes"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_collect_daily_appends_new_records(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    monkeypatch.setenv("BROWSER_USE_API_KEY", "bu-test")
    monkeypatch.setenv("BROWSER_USE_MAX_ENRICHMENTS", "0")

    city_dir = tmp_path / "data" / "cities" / "kent" / "daily"
    city_dir.mkdir(parents=True)
    merged = city_dir / "merged.csv"
    _write_csv(merged, [])  # empty initial state

    with patch("realtorfarm.collectors.collect_for_city", return_value=([KENT_RECORD], [])):
        result = subprocess.run(
            [sys.executable, "scripts/collect_daily.py", "--city", "kent", "--lookback-days", "1"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

    # collect_daily.py needs to be importable from cwd; skip subprocess for unit test
    # Test the logic directly instead:
    from scripts.collect_daily import run_collection
    run_collection(city="Kent", lookback_days=1, merged_path=merged)

    rows = list(csv.DictReader(merged.open(newline="", encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["parcel_id"] == "232204-9001"


def test_collect_daily_deduplicates_existing_records(tmp_path, monkeypatch):
    monkeypatch.setenv("BROWSER_USE_MAX_ENRICHMENTS", "0")

    city_dir = tmp_path / "data" / "cities" / "kent" / "daily"
    city_dir.mkdir(parents=True)
    merged = city_dir / "merged.csv"
    _write_csv(merged, [KENT_RECORD])  # already has this record

    from scripts.collect_daily import run_collection
    with patch("realtorfarm.collectors.collect_for_city", return_value=([KENT_RECORD], [])):
        run_collection(city="Kent", lookback_days=1, merged_path=merged)

    rows = list(csv.DictReader(merged.open(newline="", encoding="utf-8")))
    assert len(rows) == 1  # no duplicate added


def test_collect_daily_appends_only_delta(tmp_path, monkeypatch):
    monkeypatch.setenv("BROWSER_USE_MAX_ENRICHMENTS", "0")

    city_dir = tmp_path / "data" / "cities" / "kent" / "daily"
    city_dir.mkdir(parents=True)
    merged = city_dir / "merged.csv"
    _write_csv(merged, [KENT_RECORD])

    new_record = {**KENT_RECORD, "parcel_id": "232204-9999", "case_id": "KENT-2026-0200"}

    from scripts.collect_daily import run_collection
    with patch("realtorfarm.collectors.collect_for_city", return_value=([KENT_RECORD, new_record], [])):
        run_collection(city="Kent", lookback_days=1, merged_path=merged)

    rows = list(csv.DictReader(merged.open(newline="", encoding="utf-8")))
    assert len(rows) == 2
    assert {r["parcel_id"] for r in rows} == {"232204-9001", "232204-9999"}


def test_collect_daily_creates_merged_csv_if_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("BROWSER_USE_MAX_ENRICHMENTS", "0")

    merged = tmp_path / "data" / "cities" / "kent" / "daily" / "merged.csv"

    from scripts.collect_daily import run_collection
    with patch("realtorfarm.collectors.collect_for_city", return_value=([KENT_RECORD], [])):
        run_collection(city="Kent", lookback_days=1, merged_path=merged)

    assert merged.exists()
    rows = list(csv.DictReader(merged.open(newline="", encoding="utf-8")))
    assert len(rows) == 1
```

**Step 2: Run to verify failure**

```bash
pytest tests/test_collect_daily.py -v
```
Expected: FAIL — `ModuleNotFoundError` (scripts/collect_daily.py doesn't exist yet)

**Step 3: Implement**

`scripts/collect_daily.py`:
```python
#!/usr/bin/env python3
"""Collect distressed-property records for a single city and append to merged.csv."""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from realtorfarm.collectors import collect_for_city
from realtorfarm.collectors.parcel_enrichment import enrich_candidates

CANONICAL_FIELDNAMES = [
    "owner", "property_address", "parcel_id", "signal", "source", "source_url",
    "recorded_date", "case_id", "notes", "listed_status", "listing_date",
    "listing_url", "listing_source",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect and append distressed-property records")
    parser.add_argument("--city", required=True, help="City slug: burien, kent, or tukwila")
    parser.add_argument("--lookback-days", type=int, default=1, help="Days of notices to fetch")
    args = parser.parse_args()

    city_slug = args.city.strip().lower().replace(" ", "-")
    city_display = city_slug.title()
    merged_path = Path(f"data/cities/{city_slug}/daily/merged.csv")

    run_collection(city=city_display, lookback_days=args.lookback_days, merged_path=merged_path)
    return 0


def run_collection(*, city: str, lookback_days: int, merged_path: Path) -> None:
    existing = _load_existing(merged_path)
    existing_keys = {_dedupe_key(r) for r in existing}

    print(f"[collect] {city}: {len(existing)} existing records, fetching lookback={lookback_days}d")

    new_records, candidates = collect_for_city(city=city, lookback_days=lookback_days)

    max_enrichments = int(os.environ.get("BROWSER_USE_MAX_ENRICHMENTS", "10"))
    enriched = enrich_candidates(candidates, city=city, max_enrichments=max_enrichments)
    new_records.extend(enriched)

    delta = [r for r in new_records if _dedupe_key(r) not in existing_keys]
    print(f"[collect] {city}: {len(new_records)} collected, {len(delta)} net-new after dedup")

    _write_merged(merged_path, existing + delta)
    print(f"[collect] {city}: wrote {merged_path} ({len(existing) + len(delta)} total rows)")


def _dedupe_key(row: dict) -> tuple:
    return (
        row.get("parcel_id", ""),
        row.get("signal", ""),
        row.get("case_id", ""),
        row.get("source_url", ""),
    )


def _load_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _write_merged(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CANONICAL_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
```

**Step 4: Make script importable for tests**

Add `conftest.py` entry or adjust import in test. The test imports `from scripts.collect_daily import run_collection` — add `scripts/` to `pythonpath` in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src", "scripts"]
```

**Step 5: Run tests**

```bash
pytest tests/test_collect_daily.py -v
```
Expected: all 4 PASS

**Step 6: Full suite**

```bash
pytest -q
```
Expected: all pass.

**Step 7: Commit**

```bash
git add scripts/collect_daily.py tests/test_collect_daily.py pyproject.toml
git commit -m "feat: implement collect_daily.py orchestrator with append-dedup"
```

---

## Task 8: Add GitHub Actions daily workflow

**Files:**
- Create: `.github/workflows/daily.yml`

No tests needed — GitHub Actions YAML is validated by GitHub on push.

**Step 1: Create workflow**

`.github/workflows/daily.yml`:
```yaml
name: Daily distressed-property collection

on:
  schedule:
    - cron: "0 14 * * 1-5"   # 7 AM Pacific (UTC-7), Mon–Fri
  workflow_dispatch:
    inputs:
      lookback_days:
        description: "Days to look back (use 30 for initial backfill)"
        default: "1"
        required: false
      city:
        description: "Single city to run (blank = all three)"
        default: ""
        required: false

jobs:
  collect-and-score:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        city: [burien, kent, tukwila]
      fail-fast: false

    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install
        run: pip install -e ".[dev]"

      - name: Skip city if workflow_dispatch targeted a different city
        if: ${{ github.event.inputs.city != '' && github.event.inputs.city != matrix.city }}
        run: echo "Skipping ${{ matrix.city }} — targeted city is ${{ github.event.inputs.city }}" && exit 0

      - name: Collect records
        env:
          FIRECRAWL_API_KEY: ${{ secrets.FIRECRAWL_API_KEY }}
          BROWSER_USE_API_KEY: ${{ secrets.BROWSER_USE_API_KEY }}
          BROWSER_USE_MAX_ENRICHMENTS: ${{ vars.BROWSER_USE_MAX_ENRICHMENTS || '10' }}
        run: |
          python scripts/collect_daily.py \
            --city ${{ matrix.city }} \
            --lookback-days ${{ github.event.inputs.lookback_days || '1' }}

      - name: Score and upload
        env:
          BLOB_READ_WRITE_TOKEN: ${{ secrets.BLOB_READ_WRITE_TOKEN }}
        run: |
          python scripts/run_daily.py \
            --city ${{ matrix.city }} \
            --upload-blob

      - name: Commit updated merged.csv
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/cities/${{ matrix.city }}/daily/merged.csv
          git diff --cached --quiet || git commit -m "chore: daily collection ${{ matrix.city }} $(date -u +%Y-%m-%d)"
          git push
```

**Step 2: Add GitHub Secrets (do this in the GitHub repo UI)**

Go to repo → Settings → Secrets and variables → Actions:
- **Secrets:** `FIRECRAWL_API_KEY`, `BROWSER_USE_API_KEY`, `BLOB_READ_WRITE_TOKEN`
- **Variables:** `BROWSER_USE_MAX_ENRICHMENTS` = `10` (change to `0` to disable, or remove cap for production)

**Step 3: Commit**

```bash
git add .github/workflows/daily.yml
git commit -m "feat: add GitHub Actions daily collection workflow"
```

---

## Task 9: Fix hardcoded Burien references in docs/agents

**Files:**
- Modify: `agents/record-collector.md`
- Modify: `agents/source-discovery.md`
- Modify: `skills/realtorfarm/SKILL.md`
- Modify: `.claude/commands/realtorfarm.md`

**Step 1: Update `agents/record-collector.md`**

Replace contents with:
```markdown
# Record Collector Agent

Purpose: collect or guide exports from the sources in `config/cities/<city>/sources.json`.

Daily automated flow (via GitHub Actions `daily.yml`):
1. `scripts/collect_daily.py --city <city> --lookback-days 1` fetches from Firecrawl legal notice
   publications and King County Treasury, enriches missing parcel/address via Browser Use Cloud,
   and appends net-new rows to `data/cities/<city>/daily/merged.csv`.
2. `scripts/run_daily.py --city <city> --upload-blob` scores and uploads to Vercel Blob.

Manual one-off or backfill:
```bash
python scripts/collect_daily.py --city burien --lookback-days 30
python scripts/run_daily.py --city burien --upload-blob
```

Never summarize raw rows with AI; pass normalized files to the scoring script.
```

**Step 2: Update `agents/source-discovery.md`**

Replace contents with:
```markdown
# Source Discovery Agent

Purpose: find and maintain public-record sources for Burien, Kent, and Tukwila (King County, WA)
that can reveal distress before MLS/listing sites.

Active sources (Phase A+C):
- Legal notice publications (Firecrawl): South County Journal, Daily Journal of Commerce, WA Public Notice Ads
- King County Treasury tax-foreclosure list (Firecrawl)
- King County Parcel Viewer for enrichment (Browser Use Cloud)

Phase B (not yet implemented):
- Washington Courts name/case search (Browser Use Cloud) → probate, eviction, civil judgment
- King County Recorder Landmark direct (Browser Use Cloud) → same-day NOTS/NOD before publication

Rules:
- Prefer official public sources: recorder, assessor/parcel, treasury, courts, city code compliance.
- Do not scrape behind authentication unless the operator has lawful access and configures credentials.
- Return source name, URL, signal types, update cadence, and export method.
- Hand deterministic exports to scripts; do not spend AI tokens parsing rows.
```

**Step 3: Update `skills/realtorfarm/SKILL.md`**

Replace contents with:
```markdown
---
name: realtorfarm
description: Hunt Burien, Kent, and Tukwila WA distressed-property public-record signals before listings.
---

# RealtorFarm Skill

Use this skill when running or extending the distressed-property hunting system.

## Daily Workflow

1. **Collect** records for each city:
   ```bash
   python scripts/collect_daily.py --city burien --lookback-days 1
   python scripts/collect_daily.py --city kent   --lookback-days 1
   python scripts/collect_daily.py --city tukwila --lookback-days 1
   ```
   This appends net-new rows to `data/cities/<city>/daily/merged.csv`.

2. **Score and upload** for each city:
   ```bash
   python scripts/run_daily.py --city burien --upload-blob
   python scripts/run_daily.py --city kent   --upload-blob
   python scripts/run_daily.py --city tukwila --upload-blob
   ```

3. **Backfill** (first run only): use `--lookback-days 30` in collect step.

4. Run AI deep research only for outreach-qualified leads.

## Qualification Logic

- Tier 1: any signal qualifies.
- Tier 2: any signal qualifies.
- Tier 3: two Tier 3 signals qualify; one Tier 3 needs at least two Tier 4 multipliers.
- Tier 4: context only, never standalone.

## Output Contract

The final output starts with `data= ` followed by JSON containing `accessed_date` and `properties`.
```

**Step 4: Update `.claude/commands/realtorfarm.md`**

Update the `## /realtorfarm collect` section (add before `## /realtorfarm hunt`):
```markdown
## /realtorfarm collect <city> [--lookback-days N]
Collect distressed-property records for a city and append to its merged.csv:
```bash
python scripts/collect_daily.py --city <city> --lookback-days 1
```
Use `--lookback-days 30` for initial 30-day backfill. Cities: `burien`, `kent`, `tukwila`.
```

Update existing `## /realtorfarm hunt <records.csv>` example to use `--city`:
```bash
realtorfarm hunt --input data/cities/kent/daily/merged.csv --city kent \
  --max-records 99 --lookback-days 10 --evidence \
  --output out/kent/distressed-latest.json.txt
```

Update `## /realtorfarm daily <records.csv>`:
```bash
python3 scripts/run_daily.py --city burien --max-records 99 --lookback-days 10
```

**Step 5: Commit**

```bash
git add agents/ skills/ .claude/commands/realtorfarm.md
git commit -m "docs: update agents and skill for multi-city collection workflow"
```

---

## Task 10: Run 30-day backfill test

**Purpose:** Seed all three cities with baseline data before the daily cron activates.

**Step 1: Ensure env vars are set**

```bash
export FIRECRAWL_API_KEY=fc-...
export BROWSER_USE_API_KEY=bu_...
export BROWSER_USE_MAX_ENRICHMENTS=10
```

Or load from `.env.local`:
```bash
export $(grep -v '^#' src/realtorfarm/.env.local | xargs)
```

**Step 2: Run 30-day collection for all three cities**

```bash
python scripts/collect_daily.py --city burien  --lookback-days 30
python scripts/collect_daily.py --city kent    --lookback-days 30
python scripts/collect_daily.py --city tukwila --lookback-days 30
```

Expected output per city: `[collect] <City>: N collected, M net-new after dedup`

**Step 3: Verify merged.csv for each city**

```bash
python -c "
import csv
for city in ['burien', 'kent', 'tukwila']:
    rows = list(csv.DictReader(open(f'data/cities/{city}/daily/merged.csv')))
    print(f'{city}: {len(rows)} records')
"
```

Expected: non-zero counts for at least one city (may vary based on current legal notice publication content).

**Step 4: Run the full scoring pipeline to verify end-to-end**

```bash
python scripts/run_daily.py --city burien
python scripts/run_daily.py --city kent
python scripts/run_daily.py --city tukwila
```

Check `out/<city>/source-report-latest.json` — `pipeline_status` should be `active_records_found` or `records_found_but_not_outreach_qualifying` (not `empty_collector_feed`).

**Step 5: Commit any newly populated merged.csv files**

```bash
git add data/cities/
git commit -m "data: seed 30-day backfill for burien, kent, tukwila"
```

---

## Task 11: Push branch and verify CI

**Step 1: Push branch**

```bash
git push -u origin feat/multi-city-collection
```

**Step 2: Add GitHub Secrets in repo UI**

Settings → Secrets and variables → Actions → New repository secret:
- `FIRECRAWL_API_KEY`
- `BROWSER_USE_API_KEY`
- `BLOB_READ_WRITE_TOKEN`

Settings → Secrets and variables → Actions → Variables → New repository variable:
- `BROWSER_USE_MAX_ENRICHMENTS` = `10`

**Step 3: Trigger manual workflow_dispatch for backfill**

In GitHub Actions UI: Run workflow → `lookback_days: 30` → Run. Verify all three city jobs succeed.

**Step 4: Confirm source reports**

Download `out/<city>/source-report-latest.json` from the Vercel Blob or check the workflow logs. Confirm `pipeline_status != "empty_collector_feed"` for each city.

---

## Running the full test suite at any point

```bash
pytest -q
```

All tests should pass. Zero network calls are made in tests — all external calls are mocked.
