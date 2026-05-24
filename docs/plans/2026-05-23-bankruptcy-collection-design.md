# Bankruptcy Collection Design

**Date:** 2026-05-23
**Branch:** feat/multi-city-collection
**Phase:** C-B — Systematic Bankruptcy collection

---

## Problem

The `"Bankruptcy"` signal is Tier 1 (always outreach-qualifying) and is already recognized by the extractor when it appears in legal notice text. However, bankruptcy cases are filed in federal court (U.S. Bankruptcy Court, Western District of Washington — "WAWB"), not Washington State courts. The existing `courts.py` collector targets WA State courts only. Without a dedicated source, bankruptcy leads are missed unless a notice happens to mention a filing.

---

## Architecture

Two new files:

```
src/realtorfarm/collectors/courtlistener.py   ← REST wrapper (like firecrawl.py)
src/realtorfarm/collectors/bankruptcy.py       ← collector (like courts.py)
```

```
collect_bankruptcy(city, lookback_days)
    └── for chapter in [7, 11, 13]:
          ├── search_dockets("wawb", chapter, start_date, end_date)   ← paginated REST call
          └── for each docket:
                ├── get_parties(docket_id)                             ← 1 REST call per case
                ├── find debtor party → extract address + ZIP
                ├── ZIP in city's zip list → candidate (missing_parcel_id)
                └── no address available → candidate (missing_debtor_address)
```

Registered in `collectors/__init__.py` behind `BANKRUPTCY_ENABLED` env var (default `false`).

**Why candidates, not records?** Bankruptcy filings provide debtor name + address but never a parcel number. All results enter the candidates pipeline for downstream parcel enrichment (handled by existing `parcel_enrichment.py`). This is the same pattern as parcel-less REO records.

---

## City → Zip Code Mapping

Same mapping as REO:

| City | Zip codes |
|---|---|
| Burien | 98146, 98148, 98166, 98168 |
| Kent | 98030, 98031, 98032, 98042 |
| Tukwila | 98168, 98188 |

---

## CourtListener REST Wrapper (`courtlistener.py`)

**Base URL:** `https://www.courtlistener.com/api/rest/v3/`

### `search_dockets(court, chapter, date_filed_gte, date_filed_lte)`

```
GET /api/rest/v3/dockets/
    ?court=wawb
    &date_filed__gte=<start_date>
    &date_filed__lte=<end_date>
    &chapter=<7|11|13>
    &fields=id,docket_number,case_name,date_filed
    &page_size=100
```

- Returns paginated results; wrapper follows `next` links until exhausted.
- Returns `list[dict]` with keys: `id`, `docket_number`, `case_name`, `date_filed`.

### `get_parties(docket_id)`

```
GET /api/rest/v3/parties/
    ?docket=<docket_id>
    &fields=name,contact_information,party_types
```

- Returns list of party dicts.
- Debtor identified by `party_types[*].name in ("Debtor", "Joint Debtor")`.
- Address from `contact_information[0].{address1, city, state, zip_code}` (when populated).

### Rate limiting

CourtListener free tier: 5,000 requests/day, 3 req/sec. The wrapper sleeps `0.35s` between `get_parties` calls to stay within the per-second limit.

---

## Data Flow

1. `collect_bankruptcy` computes `start_date = today - max(lookback_days, 7)` (minimum 7 days to account for CourtListener's 24–48 hour indexing lag).
2. For each chapter (7, 11, 13) — wrapped in `try/except`:
   a. Call `search_dockets` → list of dockets
   b. For each docket, call `get_parties`
   c. Find the debtor party; extract address + ZIP
   d. If ZIP in `_CITY_ZIPS[city]` → build candidate with `rejection_reason="missing_parcel_id"`
   e. If no address available → build candidate with `rejection_reason="missing_debtor_address"`
3. Deduplicate by `(case_id, signal)` before returning.
4. Return `([], candidates)` — records list is always empty (no parcel available).

---

## Output Schema (candidates)

```python
{
    "property_address": "12345 6th Ave SW, Burien, WA 98146",  # debtor address (if available)
    "parcel_id":        "",
    "case_id":          "2:26-bk-00123",                        # docket_number
    "signals":          ["Bankruptcy"],
    "rejection_reason": "missing_parcel_id",                    # or "missing_debtor_address"
    "source_url":       "https://www.courtlistener.com/docket/12345678/",
    "recorded_date":    "2026-05-20",                           # date_filed
}
```

The debtor name (from `case_name`, stripped of "In re ") is stored in `notes` on the candidate for human review.

---

## `signals.json` Update

Add `"chapter 11"` alias to the `Bankruptcy` entry:

```json
"Bankruptcy": ["bankruptcy schedules", "chapter 7", "chapter 11", "chapter 13"]
```

---

## Error Handling

- `BANKRUPTCY_ENABLED` env var (default `false`) — returns `([], [])` immediately when not set.
- `COURTLISTENER_API_KEY` — raises `ValueError` when missing (same pattern as other API wrappers).
- Each chapter query wrapped in `try/except (RuntimeError, TimeoutError, OSError, ValueError)` — one chapter failing does not stop the others.
- Empty results logged: `[bankruptcy] no Chapter X filings for {city}` — not an error.
- `lookback_days` silently promoted to minimum 7 days.

---

## Integration

### `collectors/__init__.py`

```python
if os.environ.get("BANKRUPTCY_ENABLED", "").lower() == "true":
    bk_records, bk_candidates = collect_bankruptcy(city=city, lookback_days=lookback_days)
    records.extend(bk_records)
    candidates.extend(bk_candidates)
```

### `.github/workflows/daily.yml` — Collect records `env:` block

```yaml
BANKRUPTCY_ENABLED: ${{ vars.BANKRUPTCY_ENABLED || 'false' }}
COURTLISTENER_API_KEY: ${{ secrets.COURTLISTENER_API_KEY }}
```

---

## Testing

**`tests/test_collectors_bankruptcy.py`** (7 tests):

| Test | Coverage |
|------|----------|
| `test_collect_bankruptcy_returns_empty_when_disabled` | `BANKRUPTCY_ENABLED` not set → `([], [])` |
| `test_search_dockets_calls_courtlistener_once_per_chapter` | 3 docket queries (chapters 7, 11, 13) |
| `test_parse_debtor_address_filters_to_target_city_zip` | In-city ZIP kept; out-of-area ZIP discarded |
| `test_collect_bankruptcy_produces_candidate_with_missing_parcel` | In-city case → candidate `rejection_reason="missing_parcel_id"` |
| `test_collect_bankruptcy_deduplicates_same_case_across_chapters` | Same `docket_number` twice → one candidate |
| `test_collect_bankruptcy_skips_failed_chapter_and_continues` | `RuntimeError` on one chapter → others still run |
| `test_collect_bankruptcy_sends_no_address_case_to_candidates` | No debtor address → candidate `rejection_reason="missing_debtor_address"` |

**`tests/test_collect_daily.py`** — 1 new test:
- `test_collect_for_city_calls_bankruptcy_when_enabled`

---

## Files Changed

| Path | Change |
|---|---|
| `src/realtorfarm/collectors/courtlistener.py` | New file — CourtListener REST wrapper |
| `src/realtorfarm/collectors/bankruptcy.py` | New file — Bankruptcy collector |
| `src/realtorfarm/collectors/__init__.py` | Register `collect_bankruptcy` with `BANKRUPTCY_ENABLED` guard |
| `config/signals.json` | Add `"chapter 11"` alias to `Bankruptcy` |
| `.github/workflows/daily.yml` | Add `BANKRUPTCY_ENABLED` + `COURTLISTENER_API_KEY` env vars |
| `tests/test_collectors_bankruptcy.py` | New test file (7 tests) |
| `tests/test_collect_daily.py` | Add 1 integration test |

## Files Not Changed

`bankruptcy.py` and `courtlistener.py` are self-contained. `collect_daily.py`, `run_daily.py`, `ingest.py`, `scoring.py`, `output.py`, `cli.py`, `reo.py`, `courts.py`, `recorder_direct.py`, all other collectors untouched.
