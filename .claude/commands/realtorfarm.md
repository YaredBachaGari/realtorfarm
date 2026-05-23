# /realtorfarm

Distressed-property hunting command suite for Burien, Kent, and Tukwila, WA.

## /realtorfarm install
Run:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

## /realtorfarm collect <city> [--lookback-days N]
Collect distressed-property records for a city and append to its merged.csv:
```bash
python scripts/collect_daily.py --city <city> --lookback-days 1
```
Use `--lookback-days 30` for initial 30-day backfill. Cities: `burien`, `kent`, `tukwila`.

## /realtorfarm signals
Run `realtorfarm signals` to print Tier 1-4 signal definitions.

## /realtorfarm hunt <records.csv>
Run deterministic scoring without AI tokens. Defaults are set for the current test phase: fewer than 100 raw records (`--max-records 99`) and no records older than 10 days (`--lookback-days 10`).
```bash
realtorfarm hunt --input data/cities/kent/daily/merged.csv \
  --max-records 99 --lookback-days 10 --evidence \
  --output out/kent/distressed-latest.json.txt
```

## /realtorfarm scrape-notices <url-or-file>
Fetch public legal notice pages, index pages, Browser Use Cloud Landmark exports, or downloaded HTML/text files and extract distressed-property records for the target city into the requested `data= {...}` output shape. For CAPTCHA-blocked King County Recorder Landmark searches, use Browser Use Cloud to retrieve the Landmark result/detail text, enrich with King County parcel/address data when needed, save it locally, then pass that file as `--source`.
```bash
realtorfarm scrape-notices \
  --city <city> \
  --source <legal-notice-url-or-file> \
  --records-output data/normalized/public-notices.csv \
  --output out/<city>/public-notices.json.txt \
  --evidence
```

## /realtorfarm daily <records.csv>
Run validation + scoring:
```bash
python3 scripts/run_daily.py --city <city> --max-records 99 --lookback-days 10
```

## /realtorfarm research <parcel-or-owner>
Use the Deep Research Agent only after `/realtorfarm hunt` has produced an outreach-qualified lead. Cite official sources.
