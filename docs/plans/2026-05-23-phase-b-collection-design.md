# Phase B Collection Design

**Date:** 2026-05-23
**Branch:** feat/phase-b-collection
**Phase:** B — King County Recorder Landmark (direct) + Washington Courts (probate, eviction)

---

## Problem

Phase A+C collectors (legal notice publications + Treasury) are live. Two signal sources remain unimplemented:

- **Recorder Direct:** Landmark holds recordings within 24–48 hrs of filing — before newspapers publish them. This freshness gap means NOTS/NOD/Lien signals from Phase A can lag by days.
- **Courts:** Probate and Eviction signals come from case filings, not property recordings. Legal notice publications rarely cover these; courts is the authoritative source.

Both collectors were stubbed in Phase A (`courts.py`, `recorder_direct.py`) and are ready to implement.

---

## Architecture

Phase B plugs directly into the existing `collect_for_city()` registry. No changes to `collect_daily.py`, `run_daily.py`, or anything downstream.

```
collect_for_city(city, lookback_days)
    ├── [Phase A] collect_legal_notices()   ← live
    ├── [Phase C] collect_treasury()        ← live
    ├── [Phase B] collect_recorder_direct() ← NEW
    └── [Phase B] collect_courts()          ← NEW
```

Each collector is **opt-in via env var** (default `false`) so either can be enabled independently without a code push. Both are added as GitHub Actions variables alongside `BROWSER_USE_MAX_ENRICHMENTS`.

**Approach:** One Browser Use task per document/case type per city execution. Task count is bounded by the fixed set of types — no additional cap env var needed.

| Collector | Tasks per city | Signals produced |
|---|---|---|
| `recorder_direct` | 3 (NOTS, NOD, Lien) | NOTS, NOD, Lien |
| `courts` | 2 (Probate, Eviction) | Probate, Eviction |

---

## Recorder Direct (`recorder_direct.py`)

**Source:** `https://recordsearch.kingcounty.gov/LandmarkWeb/`

**Search strategy:**
1. One Browser Use task per document type, sequenced
2. Search by doc type + date range (`lookback_days` from caller; 1 for daily, 30 for backfill)
3. Filter results to records where property address contains target city
4. Return recording date, recording number, grantor, property address as plain text

**Browser Use task prompt template:**
```
Go to https://recordsearch.kingcounty.gov/LandmarkWeb/ and search for documents
of type "[DOC_TYPE]" recorded between [START_DATE] and [END_DATE].
For each result where the property address is in [CITY], WA, return:
recording date, recording number, grantor name, property address, document type.
Return as plain text, one record per line.
```

**Document types → signals:**
| Landmark doc type | Signal |
|---|---|
| `NOTICE OF TRUSTEE SALE` | `NOTS` |
| `NOTICE OF DEFAULT` | `NOD` |
| `LIEN` | `Lien` |

**Output parsing:** Recording number → `case_id`. Grantor → `owner`. Address extracted with existing city-aware regex from `parcel_enrichment.py` (imported). Records missing `parcel_id` go to candidates list for parcel enrichment.

**Env var:** `RECORDER_DIRECT_ENABLED` (default `false`).

---

## Courts (`courts.py`)

**Source:** `https://www.courts.wa.gov/index.cfm?fa=home.contentDisplay&location=nameAndCaseSearch`

**Search strategy:**
1. One Browser Use task per case type, sequenced
2. Search by case type + King County + date range
3. Filter to results where any party address contains target city
4. Return case number, filing date, case type, party names, party addresses as plain text

**Browser Use task prompt template:**
```
Go to https://www.courts.wa.gov/index.cfm?fa=home.contentDisplay&location=nameAndCaseSearch
and search for [CASE_TYPE] cases filed in King County between [START_DATE] and [END_DATE].
For each result where any party's address is in [CITY], WA, return:
case number, filing date, case type, party names, and party addresses.
Return as plain text, one record per line.
```

**Case types → signals:**
| WA Courts case type | Signal |
|---|---|
| `Probate/Guardianship/Trust` | `Probate` |
| `Unlawful Detainer` | `Eviction` |

**Output parsing:** Case number → `case_id`. Petitioner name → `owner`. Property address extracted from party addresses. `recorded_date` = filing date. Records missing `parcel_id` go to candidates list for parcel enrichment.

**Lookback:** `max(lookback_days, 7)` — courts filings take longer to appear than recorder documents; a minimum 7-day window prevents consistently empty results on daily runs.

**Env var:** `COURTS_ENABLED` (default `false`).

---

## Error Handling

- Each Browser Use task is wrapped in its own `try/except` — a failed NOTS task does not cancel NOD or Lien tasks
- Empty results for a city/type log `[collector] no [TYPE] results for [CITY]` and return `[]` — not an error
- Both collectors return `([], [])` when their env var is not set — zero overhead when disabled
- GitHub Actions: `RECORDER_DIRECT_ENABLED` and `COURTS_ENABLED` added as optional variables to the `collect-and-score` job

---

## Integration

After implementation, register both in `collectors/__init__.py`:

```python
from .recorder_direct import collect_recorder_direct
from .courts import collect_courts

def collect_for_city(city, lookback_days=1):
    ...
    if os.environ.get("RECORDER_DIRECT_ENABLED", "").lower() == "true":
        rec_records, rec_candidates = collect_recorder_direct(city=city, lookback_days=lookback_days)
        records.extend(rec_records)
        candidates.extend(rec_candidates)

    if os.environ.get("COURTS_ENABLED", "").lower() == "true":
        court_records, court_candidates = collect_courts(city=city, lookback_days=lookback_days)
        records.extend(court_records)
        candidates.extend(court_candidates)
    ...
```

---

## Testing

All Browser Use calls mocked; no live API calls in tests.

**`tests/test_collectors_recorder_direct.py`** (5 tests):
- `test_collect_recorder_direct_returns_empty_when_disabled`
- `test_collect_recorder_direct_runs_one_task_per_doc_type`
- `test_parse_recorder_output_extracts_canonical_record`
- `test_collect_recorder_direct_skips_failed_task_and_continues`
- `test_collect_recorder_direct_returns_candidates_for_missing_parcel`

**`tests/test_collectors_courts.py`** (5 tests):
- `test_collect_courts_returns_empty_when_disabled`
- `test_collect_courts_runs_one_task_per_case_type`
- `test_parse_courts_output_extracts_canonical_record`
- `test_collect_courts_skips_failed_task_and_continues`
- `test_collect_courts_uses_minimum_7_day_lookback`

**`collectors/__init__.py`** test coverage: extend existing `test_collect_daily.py` to verify Phase B collectors are called when env vars are set.

---

## Files Changed

| Path | Change |
|---|---|
| `src/realtorfarm/collectors/recorder_direct.py` | Implement (replace stub) |
| `src/realtorfarm/collectors/courts.py` | Implement (replace stub) |
| `src/realtorfarm/collectors/__init__.py` | Register Phase B collectors with env-var guard |
| `.github/workflows/daily.yml` | Add `RECORDER_DIRECT_ENABLED` and `COURTS_ENABLED` to env block |
| `tests/test_collectors_recorder_direct.py` | New test file |
| `tests/test_collectors_courts.py` | New test file |
| `tests/test_collect_daily.py` | Extend: verify Phase B collectors called when env vars set |

## Files Not Changed

`collect_daily.py`, `run_daily.py`, `ingest.py`, `scoring.py`, `output.py`, `cli.py`, all existing tests (except `test_collect_daily.py` extension above).
