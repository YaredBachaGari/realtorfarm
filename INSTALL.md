# Installation Guide


## Important Data Notice

IMPORTANT: `data/sample_records.csv` is synthetic test fixture data only. It is used only to test parsing, scoring, and output formatting. It is not extracted from King County, Burien, court, recorder, tax, probate, or listing sites, and it must never be treated as a real lead list. Real daily runs require lawful official-source exports normalized into the canonical schema.

## Requirements

- Python 3.10+
- Git
- Optional: Claude Code or another agent runner for the markdown agents/commands

## Install

```bash
git clone https://github.com/YaredBachaGari/realtorfarm.git
cd realtorfarm
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

If the GitHub repository is private or not created yet, copy this project directory and run the same commands from it.

## First Local Run

```bash
realtorfarm validate --input data/sample_records.csv
realtorfarm hunt --input data/sample_records.csv --accessed-date 2026-05-20 --evidence
python3 scripts/run_daily.py --input data/sample_records.csv
python3 scripts/validate_output.py out/burien-distressed-latest.json.txt
```

## Daily Cron Example

```cron
15 6 * * * cd /path/to/realtorfarm && . .venv/bin/activate && python3 scripts/run_daily.py --input data/daily/burien-merged.csv >> logs/daily.log 2>&1
```
