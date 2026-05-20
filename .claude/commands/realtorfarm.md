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
Run deterministic scoring without AI tokens:
```bash
realtorfarm hunt --input <records.csv> --evidence --output out/burien-distressed-latest.json.txt
```

## /realtorfarm daily <records.csv>
Run validation + scoring:
```bash
python3 scripts/run_daily.py --input <records.csv>
```

## /realtorfarm research <parcel-or-owner>
Use the Deep Research Agent only after `/realtorfarm hunt` has produced an outreach-qualified lead. Cite official sources.
