from unittest.mock import patch, MagicMock
from realtorfarm.collectors.firecrawl import scrape_url


SAMPLE_HTML = """\
<!DOCTYPE html>
<html>
<head><title>Test</title><style>body { margin: 0; }</style></head>
<body>
  <h1>Legal Notices</h1>
  <p>Notice of Trustee's Sale</p>
  <script>alert(1)</script>
  <div>More content here</div>
</body>
</html>
"""


def _mock_html_resp(html: str = SAMPLE_HTML) -> MagicMock:
    resp = MagicMock()
    resp.text = html
    resp.headers = {"Content-Type": "text/html; charset=utf-8"}
    resp.raise_for_status.return_value = None
    return resp


def test_scrape_url_makes_get_request():
    """scrape_url issues a GET (not POST) to the target URL."""
    with patch("realtorfarm.collectors.firecrawl.requests.get", return_value=_mock_html_resp()) as mock_get:
        scrape_url("https://example.com/legals")

    mock_get.assert_called_once()
    assert mock_get.call_args[0][0] == "https://example.com/legals"


def test_scrape_url_returns_text_from_html():
    """Visible body text is returned; script/style tags are stripped."""
    with patch("realtorfarm.collectors.firecrawl.requests.get", return_value=_mock_html_resp()):
        result = scrape_url("https://example.com/legals")

    assert "Legal Notices" in result
    assert "Notice of Trustee's Sale" in result
    assert "alert(1)" not in result       # <script> stripped
    assert "margin: 0" not in result      # <style> stripped


def test_scrape_url_returns_raw_text_for_non_html():
    """Non-HTML responses (CSV, plain text) are returned as-is without parsing."""
    resp = MagicMock()
    resp.text = "parcel_id,owner\n123456-0001,SMITH JOHN"
    resp.headers = {"Content-Type": "text/plain"}
    resp.raise_for_status.return_value = None

    with patch("realtorfarm.collectors.firecrawl.requests.get", return_value=resp):
        result = scrape_url("https://example.com/data.csv")

    assert "parcel_id" in result
    assert "SMITH JOHN" in result


def test_scrape_url_sends_browser_like_user_agent():
    """Request headers include a Mozilla/Chrome User-Agent string."""
    with patch("realtorfarm.collectors.firecrawl.requests.get", return_value=_mock_html_resp()) as mock_get:
        scrape_url("https://example.com/page")

    sent_headers = mock_get.call_args[1]["headers"]
    assert "Mozilla" in sent_headers.get("User-Agent", "")


def test_scrape_url_returns_empty_string_on_empty_body():
    """A page with no visible text returns an empty string."""
    html = "<html><head></head><body></body></html>"
    with patch("realtorfarm.collectors.firecrawl.requests.get", return_value=_mock_html_resp(html)):
        result = scrape_url("https://example.com/empty")

    assert result == ""
