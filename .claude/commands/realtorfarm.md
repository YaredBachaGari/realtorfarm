# /realtorfarm

Distressed-property hunting command suite for Burien, WA.

## /realtorfarm install
Run:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

## /realtorfarm signals
Run `realtorfarm signals` to print Tier 1-4 signal definitions.

## /realtorfarm hunt <records.csv>
Run deterministic scoring without AI tokens. Defaults are set for the current test phase: fewer than 100 raw records (`--max-records 99`) and no records older than 10 days (`--lookback-days 10`).
```bash
realtorfarm hunt --input <records.csv> --max-records 99 --lookback-days 10 --evidence --output out/burien-distressed-latest.json.txt
```

## /realtorfarm scrape-notices <url-or-file>
Fetch public legal notice pages, index pages, or downloaded HTML/text files and extract actual Burien distressed-property records into the requested `data= {...}` output shape.
```bash
realtorfarm scrape-notices \
  --source <legal-notice-url-or-file> \
  --records-output data/normalized/public-notices.csv \
  --output out/burien-public-notices.json.txt \
  --evidence
```

## /realtorfarm daily <records.csv>
Run validation + scoring:
```bash
python3 scripts/run_daily.py --input <records.csv> --max-records 99 --lookback-days 10
```

## /realtorfarm research <parcel-or-owner>
Use the Deep Research Agent only after `/realtorfarm hunt` has produced an outreach-qualified lead. Cite official sources.
