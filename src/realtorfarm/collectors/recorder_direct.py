from __future__ import annotations
"""Phase B stub: King County Recorder Landmark direct access via Browser Use Cloud.

When implemented, this collector will use Browser Use Cloud to navigate Landmark
(https://kingcounty.gov/en/dept/executive-services/.../recorders-office/records-search),
search by document type + date range for NOTS/NOD/Liens, download each document's text,
and pass it to the existing scrape_notice_sources_with_diagnostics() extractor.

Use this collector when legal notice publications miss a filing (usually within 24-48 hrs
of recording before newspaper publication).

Register in collectors/__init__.py collect_for_city() when ready.
"""


def collect_recorder_direct(*, city: str, lookback_days: int = 1) -> tuple[list[dict], list[dict]]:
    """Phase B — not yet implemented."""
    return [], []
