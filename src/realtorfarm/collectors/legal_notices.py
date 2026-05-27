"""Collect NOTS/NOD/Liens from public legal notice publications via Firecrawl."""
from __future__ import annotations

import tempfile
from datetime import date, timedelta
from pathlib import Path

from realtorfarm.extractors.public_notices import scrape_notice_sources_with_diagnostics
from .firecrawl import scrape_url

# DJC Trustee Sales URL with a required date parameter.
# The undated listing (cat=TR without &date=) exceeds 10 MB and causes Firecrawl 408 timeouts.
# Each per-date page is small (day's worth of notices only).
_DJC_TRUSTEE_TMPL = (
    "https://www.djc.com/notices/index.php?action=show&query=&cat=TR&date={date}"
)

# Maximum DJC date pages per run — caps Firecrawl credit usage on long backfills.
_DJC_MAX_DAYS = 7

# Static sources that don't need date filtering.
# publicnoticeads.com removed — it's a JS SPA; Firecrawl consistently returns 500.
_STATIC_SOURCES: list[str] = []

# Kept for backward-compatibility / introspection; DJC entries are date-dynamic.
LEGAL_NOTICE_SOURCES = _STATIC_SOURCES


def _build_sources(lookback_days: int) -> list[str]:
    """Return the full URL list for the given lookback window.

    DJC Trustee Sales: one date-filtered URL per day (capped at _DJC_MAX_DAYS).
    Static sources are appended after.
    """
    today = date.today()
    days = min(lookback_days, _DJC_MAX_DAYS)
    djc_urls = [
        _DJC_TRUSTEE_TMPL.format(date=(today - timedelta(days=i)).isoformat())
        for i in range(days)
    ]
    return djc_urls + list(_STATIC_SOURCES)


def collect_legal_notices(
    *,
    city: str,
    lookback_days: int = 1,
) -> tuple[list[dict[str, str]], list[dict]]:
    """Scrape legal notice publications via Firecrawl and extract target-city distress records.

    DJC Trustee Sales are fetched one day at a time (date-filtered) to stay within
    Firecrawl's response-size limit — the undated full listing is 10 MB+ and causes
    408 timeouts. lookback_days controls how many DJC date pages are fetched (max 7).
    """
    days = min(lookback_days, _DJC_MAX_DAYS)
    if lookback_days != 1:
        print(
            f"[legal_notices] lookback_days={lookback_days} — "
            f"fetching {days} DJC date pages"
        )

    temp_files: list[Path] = []
    source_paths: list[str] = []

    for url in _build_sources(lookback_days):
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
