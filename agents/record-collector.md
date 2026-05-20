# Record Collector Agent

Purpose: collect or guide exports from the sources in `config/sources.burien.json`.

Daily token-saving flow:
1. Download/export CSVs where available.
2. Save raw files under `data/raw/YYYY-MM-DD/`.
3. Run `scripts/normalize_records.py raw.csv normalized.csv`.
4. Never summarize raw rows with AI; pass normalized files to the scoring script.
