from __future__ import annotations
"""Collect Tax Delinquent 3+ Years signal from King County Treasury page via Firecrawl."""


def collect_treasury(*, city: str) -> list[dict[str, str]]:
    """Return canonical records for tax-delinquent properties in target city."""
    raise NotImplementedError
