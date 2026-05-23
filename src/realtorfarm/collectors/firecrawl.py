"""Firecrawl REST API wrapper — scrapes public web pages to markdown text."""
from __future__ import annotations

import os

import requests

FIRECRAWL_BASE = "https://api.firecrawl.dev/v1"


def scrape_url(url: str, *, api_key: str | None = None, timeout: int = 60) -> str:
    """Fetch a URL via Firecrawl and return its markdown text."""
    key = api_key or os.environ.get("FIRECRAWL_API_KEY", "")
    if not key:
        raise ValueError("FIRECRAWL_API_KEY is required")
    response = requests.post(
        f"{FIRECRAWL_BASE}/scrape",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"url": url, "formats": ["markdown"]},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json().get("data", {}).get("markdown", "")
