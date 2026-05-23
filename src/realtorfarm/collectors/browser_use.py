from __future__ import annotations
"""Browser Use Cloud REST API wrapper — runs browser tasks and returns result text."""

import os
import time
import requests

BROWSER_USE_BASE = "https://api.browser-use.com/api/v1"


def run_task(task: str, *, api_key: str | None = None, poll_interval: int = 5, timeout: int = 300) -> str:
    """Submit a Browser Use Cloud task and block until it finishes, returning the output text."""
    raise NotImplementedError
