# RealtorFarm

Agentic distressed-property hunting system for city-specific King County, Washington markets, currently Burien, Kent, and Tukwila. It is designed to find public-record distress and motivated-seller signals before they appear on listing sites.

This repository is not a web app. It is an agent + skills + scripts system: deterministic scripts do collection normalization, scoring, validation, and output rendering; AI agents are reserved for source discovery, hard browser workflows, and deep research on already-qualified leads.


## Important Data Notice

IMPORTANT: `data/sample_records.csv` is synthetic test fixture data only. It is used only to test parsing, scoring, and output formatting. It is not extracted from King County, Burien, court, recorder, tax, probate, or listing sites, and it must never be treated as a real lead list. Real daily runs require lawful official-source exports normalized into the canonical schema.

## What It Hunts

RealtorFarm labels properties using the supplied tiers:

- Tier 1 — forcing events: NOTS, probate with parcel inventory, bankruptcy schedules, REO. Always outreach-qualifying.
- Tier 2 — strong distress: NOD, lis pendens, auction scheduled, IRS lien, stacked liens, 3+ year tax delinquency on free-and-clear property. Qualifying with reasonable confidence.
- Tier 3 — moderate: expired listing, chronic code violation, mechanic/HOA lien, eviction, death of sole owner, 1-2 year tax delinquency, inherited no sale. Needs combinations.
- Tier 4 — weak multipliers: absentee/out-of-state/vacant/long tenure/developer-adjacent/mailing change/single code violation/joint-tenant death/small judgment. Context only.

## Output Format

The main command emits the requested shape:

```json
data= {
  "accessed_date": "05/20/2026",
  "properties": [
    {
      "Owner": "SYNTHETIC TEST OWNER A",
      "property address": "1000 Synthetic Fixture Ave, Burien, WA, 98166",
      "parcel id": "TEST-PARCEL-0001",
      "Signals": {"Tier_1": ["NOTS", "Probate"]}
    }
  ]
}
```

## Architecture

```text
realtorfarm/
├── agents/                     # agent role cards
│   ├── source-discovery.md
│   ├── record-collector.md
│   ├── signal-scorer.md
│   ├── deep-research.md
│   └── outreach-qa.md
├── skills/realtorfarm/SKILL.md # reusable skill for agent runners
├── .claude/commands/           # /realtorfarm command suite
├── config/
│   ├── signals.json            # shared Tier 1-4 aliases and canonical labels
│   └── cities/                 # city-specific source catalogs
│       ├── burien/sources.json
│       ├── kent/sources.json
│       └── tukwila/sources.json
├── scripts/                    # token-free daily scripts
├── src/realtorfarm/            # shared Python package
├── data/cities/                # city-specific real normalized feeds
│   ├── burien/daily/merged.csv
│   ├── kent/daily/merged.csv
│   └── tukwila/daily/merged.csv
├── data/sample_records.csv     # shared synthetic sample canonical input
└── tests/                      # pytest suite
```

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
realtorfarm hunt --input data/sample_records.csv --accessed-date 2026-05-20
```

## Commands

| Command | Purpose | Token use |
|---|---|---:|
| `/realtorfarm install` | Install package and run tests | none |
| `/realtorfarm signals` | Show Tier 1-4 signals and aliases | none |
| `/realtorfarm hunt <records.csv>` | Score and render qualified leads | none |
| `/realtorfarm scrape-notices <url-or-file>` | Fetch public legal notice pages/files and extract Burien distress leads | none |
| `/realtorfarm daily <records.csv>` | Validate + score + write latest output | none |
| `/realtorfarm research <parcel-or-owner>` | AI deep research on a qualified lead | AI only here |

Command definitions live in `.claude/commands/realtorfarm.md`.

## Canonical Input Schema

CSV or JSON rows must include:

```text
owner,property_address,parcel_id,signal,source,source_url,recorded_date,case_id,notes
```

Only the first four fields are structurally required. For the default daily/test run, `recorded_date` must be parseable (`YYYY-MM-DD`, `MM/DD/YYYY`, or `MM/DD/YY`) because undated records are excluded by the 10-day lookback guard. Use `scripts/normalize_records.py` to convert vendor/manual exports into this schema.

## Public Notice Scraping

The repository includes an implemented extractor for public legal notices that contain target-city property distress signals. It defaults to Burien and can target Kent or Tukwila with `--city Kent` / `--city Tukwila`.

Examples:

```bash
# Direct legal notice URL or local downloaded HTML/text file
realtorfarm scrape-notices --source https://example.com/legal-notice --accessed-date 2026-05-21

# Save both the requested data= JSON shape and canonical raw records
realtorfarm scrape-notices \
  --source data/raw/2026-05-21/seattle-times-notices.html \
  --records-output data/normalized/public-notices.csv \
  --output out/burien-distressed-latest.json.txt

# Follow legal-notice links from an index/search page, capped to avoid uncontrolled scraping
realtorfarm scrape-notices --source https://classifieds.seattletimes.com/wa/legals/search --max-pages 25
```

Implemented extraction currently attempts every Tier 1 and Tier 2 signal instead of focusing on a single criterion. A notice/source text can emit multiple canonical rows for the same property when multiple distress signals are present.

- Tier 1: `NOTS`, `Probate`, `Bankruptcy`, `REO`.
- Tier 2: `NOD`, `Lis Pendens`, `Auction Scheduled`, `IRS Tax Lien`, `Stacked Liens`, `Tax Delinquent 3+ Years Free-and-Clear`.
- Mechanic's lien, HOA lien, eviction/unlawful detainer where address and parcel are present.

The extractor requires a target-city property/situs address and parcel/APN before a row is emitted. It intentionally rejects notices where the target city appears only as a mailing/contact address while the labeled property address is outside the target city.

Note: King County Recorder Landmark enforces Google reCAPTCHA v2 on all searches. The pipeline's `recorder_direct` collector handles this automatically via Playwright (headless Chromium) + the 2captcha solving service. Requires `RECORDER_DIRECT_ENABLED=true` and a `TWOCAPTCHA_API_KEY` environment variable. Landmark results do not include the parcel address in the search grid — they are emitted as candidates and enriched via the King County GIS REST API (`parcel_enrichment`).

## Daily City Workflow

1. Pull official-source exports or manual search results from the source catalog in `config/cities/<city>/sources.json`.
2. Save raw files under `data/raw/YYYY-MM-DD/`.
3. Normalize each file:
   ```bash
   python3 scripts/normalize_records.py data/raw/2026-05-20/recorder.csv data/normalized/recorder.csv
   ```
4. Merge normalized files into `data/cities/<city>/daily/merged.csv`.
   The canonical feed may also include listing-status enrichment columns:
   `listed_status`, `listing_date`, `listing_url`, and `listing_source`. These columns are labels, not filters: already-listed or stale leads remain in the output with `lead_status.market_label` so reviewers can see whether the hunter was early or late.
   Public legal notice sources can now be extracted directly before merging:
   ```bash
   python3 -m realtorfarm.cli scrape-notices \
     --source data/raw/2026-05-20/legal-notices.html \
     --records-output data/normalized/public-notices.csv \
     --city Burien \
     --output out/burien/public-notices.json.txt
   ```
5. Run deterministic scoring and upload the daily `data= {...}` output to the private Vercel Blob store `distress-signal` when `BLOB_READ_WRITE_TOKEN` is available. Prefer the rolling active-leads mode for normal hunting; it uses a 30-day lookback so sparse/delayed public records do not disappear after one day:
   ```bash
   python3 scripts/run_daily.py \
     --city burien \
     --mode active \
     --max-records 99 \
     --upload-blob
   ```
   Use strict same-day delta mode only when the goal is "what was newly found today":
   ```bash
   python3 scripts/run_daily.py \
     --city burien \
     --mode delta \
     --max-records 99 \
     --upload-blob
   ```
   This reads `data/cities/burien/daily/merged.csv` by default, writes `out/burien/distressed-latest.json.txt`, writes an observability report at `out/burien/source-report-latest.json`, and uploads both `burien/YYYY-MM-DD.json.txt` and an overwritten `burien/latest.json.txt` blob. Use `--city kent` or `--city tukwila` for other markets; each reads `data/cities/<city>/daily/merged.csv` and uploads to the matching blob prefix.
6. Validate output:
   ```bash
   python3 scripts/validate_output.py out/burien/distressed-latest.json.txt
   ```
7. Send only outreach-qualified leads to the `deep-research` and `outreach-qa` agents.

## Source Catalogs

Initial official-source targets are the same county-level sources for Burien, Kent, and Tukwila, plus city-specific code-enforcement sources:

- King County Recorder online records: NOTS, NOD, liens, lis pendens, REO-related deeds.
- King County Parcel Viewer / property research: parcel, situs, owner, mailing address, tenure context.
- King County Treasury tax foreclosure pages: 3+ year delinquency and auctions.
- Washington Courts Name and Case Search / KC Script: probate, eviction, lis pendens, partition, judgments.
- City of Burien Code Compliance: chronic/unresolved code violations where public records are available.
- City of Kent Code Enforcement: chronic/unresolved code violations where public records are available.
- City of Tukwila Code Enforcement / Public Records Requests: chronic/unresolved code violations where public records are available.

## Qualification Rules Implemented

- Any Tier 1 qualifies.
- Any Tier 2 qualifies.
- Two or more Tier 3 signals qualify.
- One Tier 3 plus two or more Tier 4 multipliers qualifies.
- Tier 4 alone never qualifies.

The implementation is in `src/realtorfarm/scoring.py` and covered by tests.

## Pre-Market Methodology and Late-Lead Labels

The hunter should optimize for pre-market distress, but it must not hide stale/outdated finds. Every enriched lead can carry a `lead_status` object:

- `pre_market_candidate`: distress notice predates any known listing.
- `already_listed_before_notice`: listing predates the distress notice; keep it, but treat it as a late/outdated lead.
- `listed_same_day_as_notice`: listing and distress notice landed on the same day.
- `listed_after_notice`: distress notice came first, then the property listed.
- `listing_status_unknown`: no listing check/enrichment was supplied yet.

Zero-output city feeds are not interpreted as zero market opportunity. `out/<city>/source-report-latest.json` now includes `pipeline_status`; `empty_collector_feed` means the collector/enrichment pipeline produced no raw rows and needs source population before comparing against platforms like PropertyRadar.

Multi-parcel notices are matched to the exact unit/address when possible, so a document that mentions Unit A and Unit B parcels does not blindly emit the first parcel in the notice.

Compared with PropertyRadar, this project is still narrower: it currently depends on explicit public-record collectors and verified address/parcel rows. To close the methodology gap, source population should expand across recorder filings, assessor/tax delinquency, court/probate/lis pendens, code enforcement, and listing-status enrichment while preserving evidence and labels.

## Legal and Ethics Guardrails

Use official public records and lawful exports only. Do not infer protected-class characteristics, do not harass owners, and verify every outreach lead against official source citations before contact. This system produces research leads, not legal advice or guaranteed distress determinations.

## Expanding Later to Renton, Other Cities

Add `config/cities/<city>/sources.json` and `data/cities/<city>/daily/merged.csv`, keep the same canonical schema, and reuse the scoring/output pipeline unchanged. City-specific source agents should only change collection, not qualification criteria.
