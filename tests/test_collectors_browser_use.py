from unittest.mock import patch, MagicMock
from realtorfarm.collectors.browser_use import BrowserUseQuotaError, run_task


def _mock_response(data: dict) -> MagicMock:
    m = MagicMock()
    m.json.return_value = data
    m.raise_for_status.return_value = None
    return m


def test_run_task_returns_output_on_success():
    submit_resp = _mock_response({"id": "task_abc123"})
    poll_resp = _mock_response({"id": "task_abc123", "status": "finished", "output": "Parcel: 232204-9055\nAddress: 415 W Gowe St, Kent, WA 98032"})

    with patch("realtorfarm.collectors.browser_use.requests.post", return_value=submit_resp), \
         patch("realtorfarm.collectors.browser_use.requests.get", return_value=poll_resp):
        result = run_task("find parcel details", api_key="bu_test")

    assert "232204-9055" in result
    assert "Kent" in result


def test_run_task_polls_until_finished():
    submit_resp = _mock_response({"id": "task_xyz"})
    running_resp = _mock_response({"id": "task_xyz", "status": "running", "output": None})
    done_resp = _mock_response({"id": "task_xyz", "status": "finished", "output": "result text"})

    with patch("realtorfarm.collectors.browser_use.requests.post", return_value=submit_resp), \
         patch("realtorfarm.collectors.browser_use.requests.get", side_effect=[running_resp, done_resp]), \
         patch("realtorfarm.collectors.browser_use.time.sleep"):
        result = run_task("find parcel details", api_key="bu_test", poll_interval=1)

    assert result == "result text"


def test_run_task_raises_on_failure_status():
    import pytest
    submit_resp = _mock_response({"id": "task_fail"})
    fail_resp = _mock_response({"id": "task_fail", "status": "failed", "output": None})

    with patch("realtorfarm.collectors.browser_use.requests.post", return_value=submit_resp), \
         patch("realtorfarm.collectors.browser_use.requests.get", return_value=fail_resp):
        with pytest.raises(RuntimeError, match="failed"):
            run_task("find parcel details", api_key="bu_test")


def test_run_task_reads_api_key_from_env(monkeypatch):
    monkeypatch.setenv("BROWSER_USE_API_KEY", "bu_from_env")
    submit_resp = _mock_response({"id": "task_env"})
    done_resp = _mock_response({"id": "task_env", "status": "finished", "output": "ok"})

    with patch("realtorfarm.collectors.browser_use.requests.post", return_value=submit_resp) as mock_post, \
         patch("realtorfarm.collectors.browser_use.requests.get", return_value=done_resp):
        run_task("task")

    headers = mock_post.call_args[1]["headers"]
    assert headers.get("X-Browser-Use-API-Key") == "bu_from_env"


def test_run_task_raises_on_missing_api_key(monkeypatch):
    import pytest
    monkeypatch.delenv("BROWSER_USE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="BROWSER_USE_API_KEY"):
        run_task("task")


def test_run_task_raises_quota_error_on_402():
    import pytest
    quota_resp = MagicMock()
    quota_resp.status_code = 402
    quota_resp.raise_for_status.return_value = None

    with patch("realtorfarm.collectors.browser_use.requests.post", return_value=quota_resp):
        with pytest.raises(BrowserUseQuotaError, match="quota exhausted"):
            run_task("task", api_key="bu_test")


def test_run_task_raises_timeout_when_deadline_exceeded():
    import pytest
    submit_resp = _mock_response({"id": "task_slow"})
    running_resp = _mock_response({"id": "task_slow", "status": "running", "output": None})

    with patch("realtorfarm.collectors.browser_use.requests.post", return_value=submit_resp), \
         patch("realtorfarm.collectors.browser_use.requests.get", return_value=running_resp), \
         patch("realtorfarm.collectors.browser_use.time.sleep"), \
         patch("realtorfarm.collectors.browser_use.time.time", side_effect=[0, 0, 999]):
        with pytest.raises(TimeoutError):
            run_task("task", api_key="bu_test", timeout=1, poll_interval=1)
