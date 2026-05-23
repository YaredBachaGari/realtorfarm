"""Browser Use Cloud REST API wrapper — runs browser tasks and returns result text."""
from __future__ import annotations

import os
import time

import requests

BROWSER_USE_BASE = "https://api.browser-use.com/api/v1"


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

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    resp = requests.post(
        f"{BROWSER_USE_BASE}/run-task",
        headers=headers,
        json={"task": task},
        timeout=30,
    )
    resp.raise_for_status()
    task_id = resp.json()["id"]

    deadline = time.time() + timeout
    while time.time() < deadline:
        poll = requests.get(f"{BROWSER_USE_BASE}/task/{task_id}", headers=headers, timeout=30)
        poll.raise_for_status()
        data = poll.json()
        status = data.get("status", "")
        if status == "finished":
            return data.get("output", "") or ""
        if status == "failed":
            raise RuntimeError(f"Browser Use task {task_id} failed")
        time.sleep(poll_interval)

    raise TimeoutError(f"Browser Use task {task_id} did not finish in {timeout}s")
