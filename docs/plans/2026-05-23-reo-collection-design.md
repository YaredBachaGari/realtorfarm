# REO Collection Design

**Date:** 2026-05-23
**Branch:** feat/multi-city-collection
**Phase:** C — Systematic REO (Real Estate Owned) collection

---

## Problem

The `"REO"` signal is Tier 1 (always outreach-qualifying) and is already recognized by the extractor when it appears in legal notice text. However, REO properties do not generate legal notices once a bank takes ownership — they appear on dedicated REO listing portals. Without a systematic collector, REO leads are missed entirely unless a notice happens to mention bank-owned status.

---

## Architecture

Single `reo.py` collector, same shape as `recorder_direct.py` and `courts.py`. Registered in `collectors/__init__.py` behind `REO_ENABLED` env var (default `false`).

```
collect_reo(city, lookback_days)
    ├── _collect_hud(city)           ← Firecrawl; HUD Home Store search by zip
    ├── _collect_homepath(city)      ← Browser Use; Fannie Mae HomePath
    ├── _collect_homesteps(city)     ← Browser Use; Freddie Mac HomeSteps
    ├── _collect_wells_fargo(city)   ← Browser Use; Wells Fargo REO
    ├── _collect_chase(city)         ← Browser Use; Chase REO
    ├── _collect_bofa(city)          ← Browser Use; Bank of America REO
    └── _collect_citi(city)          ← Browser Use; Citi REO
```

Each source function fails independently. Results are internally deduplicated by `(address.lower(), signal)` before returning — a property listed on multiple portals produces one record.

---

## City → Zip Code Mapping

| City | Zip codes |
|---|---|
| Burien | 98146, 98148, 98166, 98168 |
| Kent | 98030, 98031, 98032, 98042 |
| Tukwila | 98168, 98188 |

---

## Collection Sources

### HUD Home Store — Firecrawl

- **URL pattern:** `https://www.hudhomestore.gov/Listing/PropList.aspx?sState=WA&sZip={zip}`
- **One Firecrawl call per zip code** for the target city
- Returns tabular listings; `_parse_hud_text()` extracts address, HUD case number → `case_id`
- `source="HUD Home Store"`, `source_url` = per-zip search URL

### Fannie Mae HomePath — Browser Use

- **URL:** `https://www.homepath.com/`
- One Browser Use task per city
- Task prompt: `"Go to https://www.homepath.com/ and search for homes in {city}, WA. For each listing return: full property address, list price, MLS or property ID. One property per line."`

### Freddie Mac HomeSteps — Browser Use

- **URL:** `https://www.homesteps.com/`
- Same pattern as HomePath, one task per city

### Big 4 Bank Portals — Browser Use

One task per bank per city. Task prompt template:
```
Go to {bank_reo_url} and search for REO / bank-owned properties in {city}, WA.
Return each listing as: address, property ID or loan number if shown.
One property per line.
```

Starting URLs:
- Wells Fargo: `https://reo.wellsfargo.com/`
- Chase: `https://www.chase.com/mortgage/real-estate-owned`
- BofA: `https://realestate.bankofamerica.com/reo`
- Citi: `https://www.citimortgage.com/mortgage/real-estate-owned`

Additional banks discovered during test crawls are added as new `_collect_bank_*` functions.

### `lookback_days` note

REO portals show current inventory, not a dated feed. The `lookback_days` parameter is accepted for interface consistency but is not passed to search queries — same documented limitation as `legal_notices.py`.

---

## Output Parsing

All sources use local helper functions (no cross-collector imports):

- `_extract_parcel(text)` — King County parcel regex `\b([0-9]{6}-[0-9]{4}(?:-[0-9]{2})?)\b`
- `_extract_address(text, city)` — city-aware regex first, generic street address fallback
- `_extract_case_id(text)` — HUD case numbers, MLS IDs, bank loan/property numbers
- `_extract_price(text)` → stored in `notes` as `"List price: $XXX,XXX"` (no new schema column)

REO listings typically have a full address but rarely include a parcel number. Records missing `parcel_id` go to candidates list (`rejection_reason="missing_parcel_id"`) for downstream parcel enrichment.

---

## Deduplication

**Internal (within `collect_reo`):** deduplicate by `(address.lower(), signal)` before returning — same property on multiple portals → one record, first source URL wins.

**External:** existing `(parcel_id, signal, case_id, source_url)` dedup in `collect_daily.py` handles cross-run deduplication as usual.

---

## Error Handling

- Each source wrapped in `try/except (RuntimeError, TimeoutError, OSError, ValueError)`
- Empty results logged: `[reo] no listings found for {source} in {city}` — not an error
- `REO_ENABLED` env var (default `false`) — returns `([], [])` immediately when not set
- `REO_BROWSER_USE_MAX_TASKS` env var (default `6`) — caps Browser Use calls per city run; set to `0` to disable Browser Use sources while keeping HUD/Firecrawl active

---

## Integration

Register in `collectors/__init__.py`:

```python
if os.environ.get("REO_ENABLED", "").lower() == "true":
    reo_records, reo_candidates = collect_reo(city=city, lookback_days=lookback_days)
    records.extend(reo_records)
    candidates.extend(reo_candidates)
```

Add to `.github/workflows/daily.yml` Collect records `env:` block:

```yaml
REO_ENABLED: ${{ vars.REO_ENABLED || 'false' }}
REO_BROWSER_USE_MAX_TASKS: ${{ vars.REO_BROWSER_USE_MAX_TASKS || '6' }}
```

---

## Testing

**`tests/test_collectors_reo.py`** (7 tests):

- `test_collect_reo_returns_empty_when_disabled`
- `test_collect_hud_uses_firecrawl_per_zip`
- `test_parse_hud_output_extracts_canonical_record`
- `test_collect_browser_use_sources_run_one_task_per_source`
- `test_collect_reo_deduplicates_same_property_across_sources`
- `test_collect_reo_skips_failed_source_and_continues`
- `test_collect_reo_sends_missing_parcel_to_candidates`

**`tests/test_collect_daily.py`** — add one test:
- `test_collect_for_city_calls_reo_when_enabled`

---

## Files Changed

| Path | Change |
|---|---|
| `src/realtorfarm/collectors/reo.py` | New file |
| `src/realtorfarm/collectors/__init__.py` | Register `collect_reo` with `REO_ENABLED` guard |
| `.github/workflows/daily.yml` | Add `REO_ENABLED` and `REO_BROWSER_USE_MAX_TASKS` env vars |
| `tests/test_collectors_reo.py` | New test file (7 tests) |
| `tests/test_collect_daily.py` | Add 1 integration test |

## Files Not Changed

`reo.py` is self-contained. `collect_daily.py`, `run_daily.py`, `ingest.py`, `scoring.py`, `output.py`, `cli.py`, all other collectors untouched.
