# Signal Scorer Agent

Purpose: apply the user's Tier 1-4 criteria exactly.

Use:
- `realtorfarm validate --input <records.csv>`
- `realtorfarm hunt --input <records.csv> --evidence --output out/burien-distressed-latest.json.txt`

Qualification rules are in `src/realtorfarm/scoring.py` and signal aliases are in `config/signals.json`.
