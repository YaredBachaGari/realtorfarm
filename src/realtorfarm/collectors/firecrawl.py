from __future__ import annotations
"""Firecrawl REST API wrapper — scrapes public web pages to markdown text."""

import os
import requests

FIRECRAWL_BASE = "https://api.firecrawl.dev/v1"


def scrape_url(url: str, *, api_key: str | None = None, timeout: int = 60) -> str:
    """Fetch a URL via Firecrawl and return its markdown text."""
    raise NotImplementedError
