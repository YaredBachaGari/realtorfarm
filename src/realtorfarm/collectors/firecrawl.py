"""Direct HTML fetcher — replaces Firecrawl to avoid API billing."""
from __future__ import annotations

import re
from html.parser import HTMLParser

import requests

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_SKIP_TAGS = frozenset({"script", "style", "noscript", "head", "meta", "link"})
_BLOCK_TAGS = frozenset({
    "p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6",
    "li", "tr", "td", "th", "article", "section",
})


class _TextExtractor(HTMLParser):
    """Minimal HTML → plain-text converter (stdlib only)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        raw = "".join(self._parts)
        # Collapse runs of 3+ newlines to two
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


def scrape_url(url: str, *, timeout: int = 60) -> str:
    """Fetch *url* directly via HTTP GET and return its plain-text content.

    HTML responses are stripped of tags (script/style removed entirely);
    non-HTML responses (CSV, plain text) are returned as-is.
    """
    response = requests.get(url, headers=_DEFAULT_HEADERS, timeout=timeout)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "")
    if "html" in content_type:
        parser = _TextExtractor()
        parser.feed(response.text)
        return parser.get_text()
    return response.text
