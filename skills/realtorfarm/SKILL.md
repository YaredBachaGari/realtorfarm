---
name: realtorfarm
description: Hunt Burien, Kent, and Tukwila WA distressed-property public-record signals before listings.
---

# RealtorFarm Skill

Use this skill when running or extending the distressed-property hunting system.

## Daily Workflow

1. **Collect** records for each city:
   ```bash
   python scripts/collect_daily.py --city burien --lookback-days 1
   python scripts/collect_daily.py --city kent   --lookback-days 1
   python scripts/collect_daily.py --city tukwila --lookback-days 1
   ```
   This appends net-new rows to `data/cities/<city>/daily/merged.csv`.

2. **Score and upload** for each city:
   ```bash
   python scripts/run_daily.py --city burien --upload-blob
   python scripts/run_daily.py --city kent   --upload-blob
   python scripts/run_daily.py --city tukwila --upload-blob
   ```

3. **Backfill** (first run only): use `--lookback-days 30` in collect step.

4. Run AI deep research only for outreach-qualified leads.

## Qualification Logic

- Tier 1: any signal qualifies.
- Tier 2: any signal qualifies.
- Tier 3: two Tier 3 signals qualify; one Tier 3 needs at least two Tier 4 multipliers.
- Tier 4: context only, never standalone.

## Output Contract

The final output starts with `data= ` followed by JSON containing `accessed_date` and `properties`.
