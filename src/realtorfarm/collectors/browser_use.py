"""Browser Use Cloud REST API wrapper — runs browser tasks and returns result text.

Uses API v3: https://api.browser-use.com/api/v3
Auth: X-Browser-Use-API-Key header (not Authorization: Bearer).
"""
from __future__ import annotations

import os
import time

import requests

BROWSER_USE_BASE = "https://api.browser-use.com/api/v3"

# Statuses that mean the session is still running — poll again.
_RUNNING_STATUSES = {"running", "pending", "queued"}


def run_task(
    task: str,
    *,
    api_key: str | None = None,
    poll_interval: int = 5,
    timeout: int = 300,
) -> str:
    """Submit a Browser Use Cloud task and block until finished, returning output text."""
    key = api_key or os.environ.get("BROWSER_USE_API_KEY", "")
    if not key:
        raise ValueError("BROWSER_USE_API_KEY is required")

    headers = {"X-Browser-Use-API-Key": key, "Content-Type": "application/json"}

    resp = requests.post(
        f"{BROWSER_USE_BASE}/sessions",
        headers=headers,
        json={"task": task},
        timeout=30,
    )
    resp.raise_for_status()
    session_id = resp.json()["id"]

    deadline = time.time() + timeout
    while time.time() < deadline:
        poll = requests.get(
            f"{BROWSER_USE_BASE}/sessions/{session_id}",
            headers=headers,
            timeout=30,
        )
        poll.raise_for_status()
        data = poll.json()
        status = data.get("status", "")
        if status not in _RUNNING_STATUSES:
            if status == "failed" or data.get("isTaskSuccessful") is False:
                raise RuntimeError(f"Browser Use session {session_id} failed")
            return data.get("output", "") or ""
        time.sleep(poll_interval)

    raise TimeoutError(f"Browser Use session {session_id} did not finish in {timeout}s")
