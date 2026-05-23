"""Collect NOTS/NOD/Liens from public legal notice publications via Firecrawl."""
from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from realtorfarm.extractors.public_notices import scrape_notice_sources_with_diagnostics
from .firecrawl import scrape_url

LEGAL_NOTICE_SOURCES = [
    "https://www.southcountyjournal.com/classifieds/public-notices/",
    "https://www.djc.com/legal_notices/",
    "https://www.publicnoticeads.com/wa/search/?SearchString=&county=King&category=0",
]


def collect_legal_notices(
    *,
    city: str,
    lookback_days: int = 1,
) -> tuple[list[dict[str, str]], list[dict]]:
    """Scrape legal notice publications via Firecrawl and extract target-city distress records.

    Note: lookback_days is forwarded from the orchestrator but Firecrawl always scrapes
    the current page state. Legal notice publications aggregate recent filings, so a wider
    lookback window naturally captures more history without explicit date filtering.
    """
    if lookback_days != 1:
        print(f"[legal_notices] lookback_days={lookback_days} — Firecrawl scrapes current page; broader lookback captures more publication history")
    temp_files: list[Path] = []
    source_paths: list[str] = []

    for url in LEGAL_NOTICE_SOURCES:
        try:
            text = scrape_url(url)
        except Exception as exc:
            print(f"[legal_notices] firecrawl failed for {url}: {exc}")
            continue
        if not text.strip():
            continue
        tmp = tempfile.NamedTemporaryFile(
            suffix=".md", delete=False, mode="w", encoding="utf-8"
        )
        tmp.write(text)
        tmp.close()
        temp_files.append(Path(tmp.name))
        source_paths.append(tmp.name)

    if not source_paths:
        return [], []

    try:
        records, diagnostics = scrape_notice_sources_with_diagnostics(
            source_paths,
            accessed=date.today(),
            target_city=city,
        )
    finally:
        for f in temp_files:
            f.unlink(missing_ok=True)

    return records, diagnostics.get("candidates", [])
