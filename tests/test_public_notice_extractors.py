import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from realtorfarm.extractors.public_notices import extract_notice_records, scrape_notice_sources
from realtorfarm.ingest import group_records
from realtorfarm.output import render_data


NOTICE_OF_TRUSTEE_SALE_HTML = """
<html><body><article>
<h1>NOTICE OF TRUSTEE'S SALE TS No.: 2026-00123-WA</h1>
<p>Grantor: JANE Q OWNER, a single person</p>
<p>NOTICE OF TRUSTEE'S SALE pursuant to RCW 61.24 et seq.</p>
<p>Property Address: 12345 6th Ave SW, Burien, WA 98146</p>
<p>APN: 123450-0678</p>
<p>Recorded on May 20, 2026 as Instrument No. 20260520000123.</p>
</article></body></html>
"""


PROBATE_NOTICE_HTML = """
<html><body><article>
<h1>Probate Notice to Creditors</h1>
<p>Estate of JOHN SAMPLE, deceased. Case No. 26-4-01234-1 KNT.</p>
<p>The personal representative named below has been appointed.</p>
<p>Real property commonly known as 9876 1st Ave S, Burien, WA 98148.</p>
<p>Parcel No. 987650-4321.</p>
<p>Published May 19, 2026.</p>
</article></body></html>
"""


TAX_FORECLOSURE_TITLE_TEXT = """
Litigation / Trustee's Sale / Contract Forfeiture Guarantee
Property: 11807 Military Road South, Burien, WA 98168
Tax Account No.: 309200-0235-00
Effective Date: December 8, 2017
As of the effective date, title is vested in: Robert Gardner and Aline Gardner, husband and wife.
The property has multiple years of unpaid taxes. Delinquent taxes shown herein may be subject to foreclosure by the County Treasurer.
"""


def test_extract_notice_of_trustee_sale_into_canonical_record():
    records = extract_notice_records(
        NOTICE_OF_TRUSTEE_SALE_HTML,
        source_url="https://classifieds.example.test/notice-of-trustee-sale",
        accessed=date(2026, 5, 21),
    )

    assert records == [
        {
            "owner": "JANE Q OWNER",
            "property_address": "12345 6th Ave SW, Burien, WA 98146",
            "parcel_id": "123450-0678",
            "signal": "NOTS",
            "source": "public legal notice",
            "source_url": "https://classifieds.example.test/notice-of-trustee-sale",
            "recorded_date": "2026-05-20",
            "case_id": "2026-00123-WA",
            "notes": "Extracted from public legal notice text",
        }
    ]


def test_extract_probate_notice_into_requested_output_shape():
    records = extract_notice_records(
        PROBATE_NOTICE_HTML,
        source_url="https://classifieds.example.test/probate-notice",
        accessed=date(2026, 5, 21),
    )

    rendered = render_data(group_records(records), accessed=date(2026, 5, 21))
    payload = json.loads(rendered.removeprefix("data= "))

    assert payload["accessed_date"] == "05/21/2026"
    assert payload["properties"] == [
        {
            "Owner": "JOHN SAMPLE",
            "property address": "9876 1st Ave S, Burien, WA 98148",
            "parcel id": "987650-4321",
            "Signals": {"Tier_1": ["Probate"]},
        }
    ]


def test_notice_with_non_burien_property_and_burien_mailing_address_is_rejected():
    html = """
    <h1>NOTICE OF TRUSTEE'S SALE TS No WA08001373-15-1</h1>
    <p>APN: 9006630100 More commonly known as 5920 Elizabeth Avenue SE, Auburn, WA 98092.</p>
    <p>Raeann F. Sherbourne 13634 Occidental Ave S, Burien, WA 98168</p>
    """

    assert extract_notice_records(
        html,
        source_url="https://www.tacomadailyindex.com/example",
        accessed=date(2026, 5, 21),
    ) == []


def test_extract_tax_foreclosure_title_text_into_tier_2_signal():
    records = extract_notice_records(
        TAX_FORECLOSURE_TITLE_TEXT,
        source_url="https://www.bid4assets.com/mvc/info/sfid10121/TitleReports/3092000235.pdf",
        accessed=date(2026, 5, 21),
    )

    assert records[0]["owner"] == "ROBERT GARDNER AND ALINE GARDNER"
    assert records[0]["property_address"] == "11807 Military Road South, Burien, WA 98168"
    assert records[0]["parcel_id"] == "309200-0235-00"
    assert records[0]["signal"] == "Tax Delinquent 3+ Years Free-and-Clear"
    assert records[0]["recorded_date"] == "2017-12-08"


def test_scrape_notice_sources_accepts_local_html_files(tmp_path: Path):
    notice = tmp_path / "notice.html"
    notice.write_text(NOTICE_OF_TRUSTEE_SALE_HTML, encoding="utf-8")

    records = scrape_notice_sources([str(notice)], accessed=date(2026, 5, 21))

    assert len(records) == 1
    assert records[0]["signal"] == "NOTS"
    assert records[0]["property_address"].endswith("Burien, WA 98146")


def test_cli_scrape_notices_fetches_sources_and_emits_data_shape(tmp_path: Path):
    notice = tmp_path / "notice.html"
    notice.write_text(NOTICE_OF_TRUSTEE_SALE_HTML, encoding="utf-8")

    out = subprocess.check_output(
        [
            sys.executable,
            "-m",
            "realtorfarm.cli",
            "scrape-notices",
            "--source",
            str(notice),
            "--accessed-date",
            "2026-05-21",
        ],
        text=True,
    )

    payload = json.loads(out.removeprefix("data= "))
    assert payload["properties"][0]["Owner"] == "JANE Q OWNER"
    assert payload["properties"][0]["Signals"] == {"Tier_1": ["NOTS"]}
