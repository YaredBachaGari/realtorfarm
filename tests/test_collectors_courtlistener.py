"""Tests for CourtListener retry / rate-limit behaviour."""
import pytest
import requests
from unittest.mock import patch, MagicMock

from realtorfarm.collectors.courtlistener import _get_with_retry, _MAX_RETRY_SLEEP, _rl_state


@pytest.fixture(autouse=True)
def reset_circuit_breaker():
    """Reset the module-level circuit breaker state before and after every test."""
    _rl_state["until"] = 0.0
    yield
    _rl_state["until"] = 0.0


def _make_429(retry_after: int) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 429
    resp.headers = {"Retry-After": str(retry_after)}
    resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    return resp


def _make_200() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    return resp


def test_get_with_retry_raises_immediately_when_retry_after_exceeds_cap():
    """If Retry-After > _MAX_RETRY_SLEEP, raise at once — never sleep."""
    with patch("realtorfarm.collectors.courtlistener.requests.get",
               return_value=_make_429(_MAX_RETRY_SLEEP + 1)) as mock_get, \
         patch("realtorfarm.collectors.courtlistener.time.sleep") as mock_sleep:
        with pytest.raises(requests.HTTPError):
            _get_with_retry("https://example.com", headers={})

    mock_sleep.assert_not_called()
    assert mock_get.call_count == 1  # gave up after the very first 429


def test_get_with_retry_sleeps_and_succeeds_within_cap():
    """If Retry-After <= _MAX_RETRY_SLEEP, sleep and retry; succeed on 2nd attempt."""
    responses = [_make_429(_MAX_RETRY_SLEEP), _make_200()]
    with patch("realtorfarm.collectors.courtlistener.requests.get",
               side_effect=responses), \
         patch("realtorfarm.collectors.courtlistener.time.sleep") as mock_sleep:
        result = _get_with_retry("https://example.com", headers={})

    mock_sleep.assert_called_once_with(_MAX_RETRY_SLEEP)
    assert result.status_code == 200


def test_get_with_retry_cap_boundary_exactly_equal():
    """Retry-After == _MAX_RETRY_SLEEP should sleep (not raise immediately)."""
    responses = [_make_429(_MAX_RETRY_SLEEP), _make_200()]
    with patch("realtorfarm.collectors.courtlistener.requests.get",
               side_effect=responses), \
         patch("realtorfarm.collectors.courtlistener.time.sleep") as mock_sleep:
        _get_with_retry("https://example.com", headers={})

    mock_sleep.assert_called_once()


# ── Circuit-breaker tests ─────────────────────────────────────────────────────

def test_circuit_breaker_armed_after_large_retry_after():
    """A 429 with Retry-After > cap should arm the circuit breaker."""
    import time
    _rl_state["until"] = 0.0  # reset before test
    with patch("realtorfarm.collectors.courtlistener.requests.get",
               return_value=_make_429(_MAX_RETRY_SLEEP + 1)), \
         patch("realtorfarm.collectors.courtlistener.time.sleep"):
        with pytest.raises(requests.HTTPError):
            _get_with_retry("https://example.com", headers={})

    assert _rl_state["until"] > time.monotonic(), "circuit breaker must be set to a future time"


def test_circuit_breaker_skips_network_when_active():
    """When the circuit breaker is active, no network call is made."""
    import time
    _rl_state["until"] = time.monotonic() + 1800  # simulate active circuit breaker
    try:
        with patch("realtorfarm.collectors.courtlistener.requests.get") as mock_get:
            with pytest.raises(requests.HTTPError, match="circuit breaker"):
                _get_with_retry("https://example.com", headers={})

        mock_get.assert_not_called()
    finally:
        _rl_state["until"] = 0.0  # always reset so other tests are unaffected


def test_circuit_breaker_clears_after_window_expires():
    """An expired circuit breaker does not prevent the next request."""
    import time
    _rl_state["until"] = time.monotonic() - 1  # expired 1 second ago
    with patch("realtorfarm.collectors.courtlistener.requests.get",
               return_value=_make_200()):
        result = _get_with_retry("https://example.com", headers={})

    assert result.status_code == 200
