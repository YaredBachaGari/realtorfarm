from unittest.mock import patch
from realtorfarm.collectors.treasury import collect_treasury, TREASURY_URL


TREASURY_MARKDOWN = """
# King County Tax Foreclosure Properties

The following properties are subject to tax foreclosure:

| Parcel Number | Owner Name | Situs Address | Years Delinquent |
|---|---|---|---|
| 232204-9055 | KENT DELINQUENT OWNER LLC | 415 W Gowe St, Kent, WA 98032 | 4 |
| 123450-0999 | BURIEN DELINQUENT OWNER | 10001 15th Ave SW, Burien, WA 98146 | 3 |
| 004000-0200 | TUKWILA DELINQUENT OWNER | 14500 Interurban Ave S, Tukwila, WA 98168 | 5 |
| 000100-0001 | RENTON OWNER | 100 Main Ave S, Renton, WA 98057 | 3 |
"""


def test_collect_treasury_returns_kent_parcels_only():
    with patch("realtorfarm.collectors.treasury.scrape_url", return_value=TREASURY_MARKDOWN):
        records = collect_treasury(city="Kent")

    assert len(records) == 1
    assert records[0]["signal"] == "Tax Delinquent 3+ Years Free-and-Clear"
    assert "Kent" in records[0]["property_address"]
    assert records[0]["parcel_id"] == "232204-9055"
    assert records[0]["owner"] == "KENT DELINQUENT OWNER LLC"


def test_collect_treasury_excludes_other_cities():
    with patch("realtorfarm.collectors.treasury.scrape_url", return_value=TREASURY_MARKDOWN):
        records = collect_treasury(city="Kent")

    addresses = [r["property_address"] for r in records]
    assert not any("Renton" in a for a in addresses)
    assert not any("Burien" in a for a in addresses)


def test_collect_treasury_returns_burien_records():
    with patch("realtorfarm.collectors.treasury.scrape_url", return_value=TREASURY_MARKDOWN):
        records = collect_treasury(city="Burien")

    assert len(records) == 1
    assert "Burien" in records[0]["property_address"]


def test_collect_treasury_returns_empty_on_scrape_failure():
    with patch("realtorfarm.collectors.treasury.scrape_url", side_effect=Exception("timeout")):
        records = collect_treasury(city="Kent")

    assert records == []


def test_treasury_url_is_king_county_official():
    assert "kingcounty.gov" in TREASURY_URL
