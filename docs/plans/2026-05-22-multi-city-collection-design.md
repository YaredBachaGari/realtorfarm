# Multi-City Automated Collection Design

**Date:** 2026-05-22  
**Branch:** feat/multi-city-collection  
**Phase:** A+C (Recorder signals via legal notice publications + Treasury tax delinquent); Phase B stubs included for courts and direct Landmark access

---

## Problem

Kent and Tukwila `merged.csv` files are empty — the deterministic pipeline (validate → hunt → score → report → blob) is working correctly but has no input. Burien has one record from a single manually-fetched notice file. The collection step was never automated or extended to all three cities.

Secondary gaps found during root-cause analysis:
- `target_city` defaults to `"Burien"` across extractors and CLI — multi-city runs silently misfires if `--city` is omitted
- `record-collector.md` references a stale config path (`config/sources.burien.json`)
- Address + parcel extraction in `public_notices.py` silently drops notices missing either field — the main source of candidate rejections

---

## Architecture

A new **collection layer** sits upstream of the existing deterministic pipeline. `run_daily.py`, `ingest.py`, `scoring.py`, `output.py`, and `cli.py` are untouched.

```
[GitHub Actions cron — 0 14 * * 1-5 (7 AM Pacific, Mon–Fri)]
           ↓  matrix: [burien, kent, tukwila], fail-fast: false
scripts/collect_daily.py --city <city> [--lookback-days N]
           ↓
 ┌──────────────────────────────────────────────────────┐
 │  Firecrawl: legal notice publications                │  NOTS, NOD, Liens,
 │    - South County Journal (legals section)           │  Lis Pendens, REO
 │    - Daily Journal of Commerce (legal notices)       │
 │    - WA Public Notice Ads (King County filter)       │
 │  Firecrawl: King County Treasury tax-foreclosure     │  Tax Delinquent 3+yrs
 └──────────────────────────────────────────────────────┘
           ↓
  scrape_notice_sources_with_diagnostics(sources, target_city=city)
           ↓  candidates with missing_parcel_id | missing_target_city_property_address
 ┌──────────────────────────────────────────────────────┐
 │  Browser Use Cloud: King County Parcel Viewer        │  fills situs address
 │    - capped at BROWSER_USE_MAX_ENRICHMENTS (default  │  + parcel ID
 │      10 during testing; env-var controlled)          │
 └──────────────────────────────────────────────────────┘
           ↓  append net-new rows, deduplicate by (parcel_id, signal, case_id, source_url)
  data/cities/<city>/daily/merged.csv   ← accumulates across runs, no overwrite
           ↓
  run_daily.py --city <city> --upload-blob
           ↓
  Vercel Blob: <city>/YYYY-MM-DD.json.txt (immutable dated snapshot)
              <city>/latest.json.txt      (overwritten each run)
```

---

## Components

### New files

| Path | Purpose |
|---|---|
| `src/realtorfarm/collectors/__init__.py` | Active collector registry; Phase B collectors imported here when ready |
| `src/realtorfarm/collectors/firecrawl.py` | Firecrawl API wrapper (`scrape`, `crawl` modes) |
| `src/realtorfarm/collectors/browser_use.py` | Browser Use Cloud API wrapper (task creation + result polling) |
| `src/realtorfarm/collectors/legal_notices.py` | Firecrawl → legal notice publications → canonical rows |
| `src/realtorfarm/collectors/treasury.py` | Firecrawl → King County Treasury tax-delinquent list → canonical rows |
| `src/realtorfarm/collectors/parcel_enrichment.py` | Browser Use → King County Parcel Viewer → fills address + parcel for rejected candidates |
| `src/realtorfarm/collectors/courts.py` | **STUB — Phase B:** Washington Courts name/case search (probate, eviction) |
| `src/realtorfarm/collectors/recorder_direct.py` | **STUB — Phase B:** Browser Use against King County Recorder Landmark |
| `scripts/collect_daily.py` | Orchestrator: runs active collectors, merges delta, enriches candidates, appends to merged.csv |
| `.github/workflows/daily.yml` | Scheduled cron + manual dispatch; matrix over cities |

### Modified files

| Path | Change |
|---|---|
| `agents/record-collector.md` | Update stale config path reference |
| `agents/source-discovery.md` | Expand scope from Burien-only to multi-city |
| `skills/realtorfarm/SKILL.md` | Update description + workflow steps for multi-city |
| `.claude/commands/realtorfarm.md` | Update examples to pass `--city` |

---

## Collection Sources (Phase A+C)

### Legal notice publications — Firecrawl

Washington state law (RCW 61.24) requires NOTS to be published in a newspaper of general circulation for 8 consecutive weeks. King County notices appear in:

- **South County Journal** — primary coverage for Burien, Kent, Tukwila area
- **Daily Journal of Commerce** — county-wide NOTS, NOD, Liens, Lis Pendens, REO
- **WA Public Notice Ads** — aggregator, King County filter

Firecrawl returns clean markdown text. This is fed directly into the existing `scrape_notice_sources_with_diagnostics(sources, target_city=city)` — no new parser needed.

### King County Treasury — Firecrawl

Semi-static HTML page at `kingcounty.gov/…/tax-foreclosures`. `treasury.py` parses the table (owner, parcel, delinquency year) and emits rows with `signal="Tax Delinquent 3+ Years Free-and-Clear"`.

### Multi-city filtering

All sources are King County-wide. `target_city` is passed explicitly on every call to `scrape_notice_sources_with_diagnostics()`. The existing `_mentions_target_city()` regex (`\b<City>\b\s*,?\s*(?:WA|Washington)\b`) already handles filtering correctly. GitHub Actions matrix runs each city independently.

---

## Browser Use Enrichment

After the Firecrawl pass, `collect_daily.py` inspects the `candidates` list from the extractor diagnostics. Enrichment is called only for candidates with:

- `rejection_reason == "missing_parcel_id"` — has address but no parcel; Browser Use queries Parcel Viewer by address
- `rejection_reason == "missing_target_city_property_address"` — has parcel/case ID but no address; Browser Use queries Parcel Viewer by parcel number or owner name

Candidates with `missing_distress_signal` or `missing_target_city` are discarded — no Browser Use call wasted.

**Cap:** `BROWSER_USE_MAX_ENRICHMENTS` env var (default `10`). Set to `0` to disable, remove cap for production.

---

## Accumulation & Deduplication

`collect_daily.py` never overwrites `merged.csv`. Each run:

1. Loads existing `merged.csv` rows (prior accumulated records)
2. Collects today's delta from all active collectors
3. Deduplicates by `(parcel_id, signal, case_id, source_url)` — same key as `_dedupe_records()` in `public_notices.py`
4. Appends only net-new rows and writes back

`run_daily.py --lookback-days` then windows what gets scored. Vercel Blob output:
- Dated snapshot: `<city>/YYYY-MM-DD.json.txt` — immutable, one per run
- Latest: `<city>/latest.json.txt` — overwritten each run

---

## Foundational Backfill Test

Before activating the daily cron, run once with:

```bash
python scripts/collect_daily.py --city burien --lookback-days 30
python scripts/collect_daily.py --city kent   --lookback-days 30
python scripts/collect_daily.py --city tukwila --lookback-days 30
```

Or via `workflow_dispatch` in GitHub Actions (the workflow exposes `lookback_days` as an input). This seeds each city's `merged.csv` with 30 days of baseline data. The daily cron then runs in delta mode (`--lookback-days 1`).

---

## GitHub Actions Workflow

```yaml
on:
  schedule:
    - cron: "0 14 * * 1-5"   # 7 AM Pacific, Mon–Fri
  workflow_dispatch:
    inputs:
      lookback_days:
        description: "Days to look back (use 30 for backfill)"
        default: "1"
      city:
        description: "City to run (leave blank for all)"
        default: ""

jobs:
  collect-and-score:
    strategy:
      matrix:
        city: [burien, kent, tukwila]
      fail-fast: false         # one city failing does not cancel others
    env:
      FIRECRAWL_API_KEY: ${{ secrets.FIRECRAWL_API_KEY }}
      BROWSER_USE_API_KEY: ${{ secrets.BROWSER_USE_API_KEY }}
      BLOB_READ_WRITE_TOKEN: ${{ secrets.BLOB_READ_WRITE_TOKEN }}
      BROWSER_USE_MAX_ENRICHMENTS: ${{ vars.BROWSER_USE_MAX_ENRICHMENTS || '10' }}
    steps:
      - collect_daily.py --city ${{ matrix.city }}
        --lookback-days ${{ inputs.lookback_days || '1' }}
      - run_daily.py --city ${{ matrix.city }} --upload-blob
      - git commit + push updated merged.csv
```

Secrets (`FIRECRAWL_API_KEY`, `BROWSER_USE_API_KEY`, `BLOB_READ_WRITE_TOKEN`) are stored in GitHub Secrets. `BROWSER_USE_MAX_ENRICHMENTS` is a GitHub Actions variable (not secret) so it can be changed without a code push.

---

## Error Handling

- Each collector fails independently; exceptions are caught, logged, and skipped
- A city that produces zero records writes an empty CSV header and exits 0 — `reporting.py` surfaces this as `empty_collector_feed`
- Browser Use enrichment failures per-candidate are logged and skipped; the cap ensures the run completes in bounded time
- GitHub Actions `fail-fast: false` ensures all three cities always run

---

## Phase B Stubs

`courts.py` and `recorder_direct.py` are committed as stubs with docstrings describing inputs/outputs. Adding Phase B is: implement the stub → register it in `collectors/__init__.py` → done. No orchestrator changes needed.

---

## Files Not Changed

`run_daily.py`, `ingest.py`, `scoring.py`, `output.py`, `cli.py`, all existing tests, all `config/cities/*/sources.json` files.
