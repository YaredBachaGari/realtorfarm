# Record Collector Agent

Purpose: collect or guide exports from the sources in `config/cities/<city>/sources.json`.

Daily automated flow (via GitHub Actions `daily.yml`):
1. `scripts/collect_daily.py --city <city> --lookback-days 1` fetches from Firecrawl legal notice
   publications and King County Treasury, enriches missing parcel/address via Browser Use Cloud,
   and appends net-new rows to `data/cities/<city>/daily/merged.csv`.
2. `scripts/run_daily.py --city <city> --upload-blob` scores and uploads to Vercel Blob.

Manual one-off or backfill:
```bash
python scripts/collect_daily.py --city <city> --lookback-days 30
python scripts/run_daily.py --city <city> --upload-blob
```

Never summarize raw rows with AI; pass normalized files to the scoring script.
