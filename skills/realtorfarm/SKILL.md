---
name: realtorfarm
description: Hunt Burien WA distressed-property public-record signals before listings.
---

# RealtorFarm Skill

Use this skill when running or extending the distressed-property hunting system.

## Daily Workflow

1. Collect official-source exports into `data/raw/YYYY-MM-DD/`.
2. Normalize each export with `scripts/normalize_records.py`.
3. Merge normalized rows into one CSV with canonical columns.
4. Run `python scripts/run_daily.py --input <merged.csv> --max-records 99 --lookback-days 10`.
   During the Burien test phase, keep extraction under 100 raw records and restrict records to the most recent 10 days from the run/accessed date.
5. Validate output with `python scripts/validate_output.py out/burien-distressed-latest.json.txt`.
6. Run AI deep research only for outreach-qualified leads.

## Qualification Logic

- Tier 1: any signal qualifies.
- Tier 2: any signal qualifies.
- Tier 3: two Tier 3 signals qualify; one Tier 3 needs at least two Tier 4 multipliers.
- Tier 4: context only, never standalone.

## Output Contract

The final output starts with `data= ` followed by JSON containing `accessed_date` and `properties`.
