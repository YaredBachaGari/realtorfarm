# RealtorFarm

Agentic distressed-property hunting system for Burien, Washington. It is designed to find public-record distress and motivated-seller signals before they appear on listing sites.

This repository is not a web app. It is an agent + skills + scripts system: deterministic scripts do collection normalization, scoring, validation, and output rendering; AI agents are reserved for source discovery, hard browser workflows, and deep research on already-qualified leads.

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
      "Owner": "John Doe2",
      "property address": "123 4th ave, Burien, WA, 98166",
      "parcel id": "0001000001",
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
│   ├── signals.json            # Tier 1-4 aliases and canonical labels
│   └── sources.burien.json     # Burien/King County source catalog
├── scripts/                    # token-free daily scripts
├── src/realtorfarm/            # Python package
├── data/sample_records.csv     # sample canonical input
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
| `/realtorfarm daily <records.csv>` | Validate + score + write latest output | none |
| `/realtorfarm research <parcel-or-owner>` | AI deep research on a qualified lead | AI only here |

Command definitions live in `.claude/commands/realtorfarm.md`.

## Canonical Input Schema

CSV or JSON rows must include:

```text
owner,property_address,parcel_id,signal,source,source_url,recorded_date,case_id,notes
```

Only the first four fields are required. Use `scripts/normalize_records.py` to convert vendor/manual exports into this schema.

## Daily Burien Workflow

1. Pull official-source exports or manual search results from the source catalog in `config/sources.burien.json`.
2. Save raw files under `data/raw/YYYY-MM-DD/`.
3. Normalize each file:
   ```bash
   python3 scripts/normalize_records.py data/raw/2026-05-20/recorder.csv data/normalized/recorder.csv
   ```
4. Merge normalized files into `data/daily/burien-merged.csv`.
5. Run deterministic scoring:
   ```bash
   python3 scripts/run_daily.py --input data/daily/burien-merged.csv
   ```
6. Validate output:
   ```bash
   python3 scripts/validate_output.py out/burien-distressed-latest.json.txt
   ```
7. Send only outreach-qualified leads to the `deep-research` and `outreach-qa` agents.

## Source Catalog for Burien

Initial official-source targets:

- King County Recorder online records: NOTS, NOD, liens, lis pendens, REO-related deeds.
- King County Parcel Viewer / property research: parcel, situs, owner, mailing address, tenure context.
- King County Treasury tax foreclosure pages: 3+ year delinquency and auctions.
- Washington Courts Name and Case Search / KC Script: probate, eviction, lis pendens, partition, judgments.
- City of Burien Code Compliance: chronic/unresolved code violations where public records are available.

## Qualification Rules Implemented

- Any Tier 1 qualifies.
- Any Tier 2 qualifies.
- Two or more Tier 3 signals qualify.
- One Tier 3 plus two or more Tier 4 multipliers qualifies.
- Tier 4 alone never qualifies.

The implementation is in `src/realtorfarm/scoring.py` and covered by tests.

## Legal and Ethics Guardrails

Use official public records and lawful exports only. Do not infer protected-class characteristics, do not harass owners, and verify every outreach lead against official source citations before contact. This system produces research leads, not legal advice or guaranteed distress determinations.

## Expanding Later to Kent, Renton, Tukwila

Add a new source catalog file such as `config/sources.kent.json`, keep the same canonical schema, and reuse the scoring/output pipeline unchanged. City-specific source agents should only change collection, not qualification criteria.
