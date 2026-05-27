from unittest.mock import patch, MagicMock
from realtorfarm.collectors.firecrawl import scrape_url


MOCK_FIRECRAWL_RESPONSE = {
    "success": True,
    "data": {
        "markdown": "# Legal Notices\n\nNotice of Trustee's Sale...",
        "metadata": {"statusCode": 200},
    },
}


def test_scrape_url_returns_markdown_text():
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_FIRECRAWL_RESPONSE
    mock_resp.raise_for_status.return_value = None

    with patch("realtorfarm.collectors.firecrawl.requests.post", return_value=mock_resp) as mock_post:
        result = scrape_url("https://example.com/legals", api_key="fc-test")

    assert result == "# Legal Notices\n\nNotice of Trustee's Sale..."
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "https://api.firecrawl.dev/v1/scrape" in call_kwargs[0][0]
    assert call_kwargs[1]["json"]["url"] == "https://example.com/legals"


def test_scrape_url_reads_api_key_from_env(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-from-env")
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_FIRECRAWL_RESPONSE
    mock_resp.raise_for_status.return_value = None

    with patch("realtorfarm.collectors.firecrawl.requests.post", return_value=mock_resp) as mock_post:
        scrape_url("https://example.com/legals")

    headers = mock_post.call_args[1]["headers"]
    assert "fc-from-env" in headers["Authorization"]


def test_scrape_url_raises_on_missing_api_key(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    import pytest
    with pytest.raises(ValueError, match="FIRECRAWL_API_KEY"):
        scrape_url("https://example.com/legals")


def test_scrape_url_returns_empty_string_on_missing_markdown():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"success": True, "data": {}}
    mock_resp.raise_for_status.return_value = None

    with patch("realtorfarm.collectors.firecrawl.requests.post", return_value=mock_resp):
        result = scrape_url("https://example.com/legals", api_key="fc-test")

    assert result == ""
