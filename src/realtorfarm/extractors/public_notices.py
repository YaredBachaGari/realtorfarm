from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

CANONICAL_COLUMNS = [
    "owner",
    "property_address",
    "parcel_id",
    "signal",
    "source",
    "source_url",
    "recorded_date",
    "case_id",
    "notes",
]

USER_AGENT = "RealtorFarm/0.1 (+public-record research; contact repository owner)"
DISTRESS_TERMS = (
    "tax delinquent",
    "delinquent taxes",
    "unpaid taxes",
    "property tax foreclosure",
    "notice of trustee",
    "trustee's sale",
    "trustee sale",
    "notice of default",
    "lis pendens",
    "probate notice",
    "notice to creditors",
    "estate of",
    "federal tax lien",
    "mechanic",
    "hoa lien",
    "homeowners association lien",
    "unlawful detainer",
    "eviction",
)


def scrape_notice_sources(sources: list[str], *, accessed: date | None = None, max_pages: int = 25) -> list[dict[str, str]]:
    """Fetch URL/file legal notices and return canonical rows for Burien distress signals.

    Sources may be:
    - direct public legal notice URLs,
    - local HTML/text fixtures or downloaded notice files,
    - index/search pages containing links to individual notice pages.
    """
    accessed = accessed or date.today()
    records: list[dict[str, str]] = []
    seen: set[str] = set()

    for source in sources:
        for page_source, text in _source_pages(source, max_pages=max_pages):
            if page_source in seen:
                continue
            seen.add(page_source)
            records.extend(extract_notice_records(text, source_url=page_source, accessed=accessed))

    return _dedupe_records(records)


def extract_notice_records(text: str, *, source_url: str, accessed: date | None = None) -> list[dict[str, str]]:
    """Extract Burien distress-property rows from public legal notice text or HTML."""
    accessed = accessed or date.today()
    plain = normalize_notice_text(text)
    if not _mentions_burien(plain) or not _contains_distress_signal(plain):
        return []

    signal = _detect_signal(plain)
    if not signal:
        return []

    address = _extract_address(plain)
    parcel_id = _extract_parcel_id(plain)
    owner = _extract_owner(plain, signal=signal)
    case_id = _extract_case_id(plain)
    recorded_date = _extract_recorded_date(plain) or accessed.isoformat()

    if not address or not parcel_id:
        return []

    return [
        _canonical_record(
            owner=owner,
            property_address=address,
            parcel_id=parcel_id,
            signal=signal,
            source_url=source_url,
            recorded_date=recorded_date,
            case_id=case_id,
        )
    ]


def normalize_notice_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", text)
    text = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</tr>|</h[1-6]>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _source_pages(source: str, *, max_pages: int) -> list[tuple[str, str]]:
    text = _read_source(source)
    pages = [(source, text)]
    if len(pages) >= max_pages:
        return pages

    # If the source is an index/search page, follow likely legal-notice links on the same host.
    for link in _extract_notice_links(text, base_url=source):
        if len(pages) >= max_pages:
            break
        try:
            page = _read_source(link)
        except Exception:
            continue
        if _looks_like_distress_notice(page):
            pages.append((link, page))
    return pages


def _read_source(source: str) -> str:
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme in {"http", "https"}:
        req = urllib.request.Request(source, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            content_type = response.headers.get("content-type", "")
        encoding = "utf-8"
        match = re.search(r"charset=([^;]+)", content_type, re.I)
        if match:
            encoding = match.group(1).strip()
        return raw.decode(encoding, errors="ignore")
    return Path(source).read_text(encoding="utf-8", errors="ignore")


def _extract_notice_links(text: str, *, base_url: str) -> list[str]:
    links: list[str] = []
    for raw in re.findall(r"(?i)href=[\"']([^\"'#]+)", text):
        absolute = urllib.parse.urljoin(base_url, raw)
        lowered = absolute.lower()
        if any(token in lowered for token in ("/legals/", "legal-notice", "notice")):
            links.append(absolute)
    return list(dict.fromkeys(links))


def _looks_like_distress_notice(text: str) -> bool:
    plain = normalize_notice_text(text).lower()
    return any(term in plain for term in DISTRESS_TERMS)


def _mentions_burien(text: str) -> bool:
    return re.search(r"\bBurien\b\s*,?\s*WA\b|\bBurien\b\s*,?\s*Washington\b", text, re.I) is not None


def _contains_distress_signal(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in DISTRESS_TERMS)


def _detect_signal(text: str) -> str | None:
    lowered = text.lower()
    if (
        "tax delinquent" in lowered
        or "delinquent taxes" in lowered
        or "unpaid taxes" in lowered
        or "property tax foreclosure" in lowered
    ):
        return "Tax Delinquent 3+ Years Free-and-Clear"
    if "notice of trustee" in lowered or "trustee's sale" in lowered or "trustee sale" in lowered:
        return "NOTS"
    if "notice of default" in lowered:
        return "NOD"
    if "lis pendens" in lowered:
        return "Lis Pendens"
    if "probate notice" in lowered or "notice to creditors" in lowered or re.search(r"\bestate of\b", lowered):
        return "Probate"
    if "federal tax lien" in lowered or "irs lien" in lowered:
        return "IRS Tax Lien"
    if "mechanic" in lowered and "lien" in lowered:
        return "Mechanic's Lien"
    if "hoa lien" in lowered or "homeowners association lien" in lowered:
        return "HOA Lien"
    if "unlawful detainer" in lowered or "eviction" in lowered:
        return "Eviction"
    return None


def _extract_address(text: str) -> str:
    labeled = re.search(
        r"(?:property address|common address|situs address|property|commonly known as|more commonly known as)\s*[:\-]?\s*([^\n.;]+?(?:\b[A-Z][a-z]+\b\s*,?\s*WA(?:shington)?\s+\d{5}(?:-\d{4})?))",
        text,
        re.I,
    )
    if labeled:
        candidate = _clean_value(labeled.group(1))
        candidate = re.sub(r"^(?:commonly|more commonly)\s+known\s+as\s+", "", candidate, flags=re.I)
        return candidate if re.search(r"\bBurien\b\s*,?\s*WA", candidate, re.I) else ""

    patterns = [
        r"((?:\d{1,6}\s+[^\n.;]{2,80}?\b(?:Ave|Avenue|St|Street|Rd|Road|Dr|Drive|Ln|Lane|Ct|Court|Pl|Place|Way|Blvd|Boulevard|Ter|Terrace|Cir|Circle)\b[^\n.;]{0,60}?\bBurien\b\s*,?\s*WA(?:shington)?\s+\d{5}(?:-\d{4})?))",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return _clean_value(match.group(1))

    lines = [_clean_value(line) for line in text.splitlines() if _clean_value(line)]
    street_re = re.compile(r"^\d{1,6}\s+.+\b(?:Ave|Avenue|St|Street|Rd|Road|Dr|Drive|Ln|Lane|Ct|Court|Pl|Place|Way|Blvd|Boulevard|Ter|Terrace|Cir|Circle)\b", re.I)
    for index, line in enumerate(lines[:-1]):
        next_line = lines[index + 1]
        if street_re.search(line) and re.search(r"\bBurien\b\s*,?\s*WA(?:shington)?\s+\d{5}(?:-\d{4})?", next_line, re.I):
            return f"{line}, {next_line}"
    return ""


def _extract_parcel_id(text: str) -> str:
    patterns = [
        r"\b(?:APN|Parcel(?:\s+(?:No\.?|Number|ID|ID\(s\)))?|Tax\s+(?:Parcel|Account)(?:\s+(?:No\.?|Number))?)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9\-]{4,25})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return _clean_value(match.group(1)).rstrip(".,;")
    return ""


def _extract_owner(text: str, *, signal: str) -> str:
    if signal == "Probate":
        match = re.search(r"\bEstate\s+of\s+([^,.;\n]+)(?:\s*,\s*(?:deceased|decendent|decedent))?", text, re.I)
        if match:
            return _clean_owner(match.group(1))
    patterns = [
        r"\b(?:Grantor|Trustor|Borrower|Owner)\s*[:\-]\s*([^\n.;]+)",
        r"\btitle\s+is\s+vested\s+in\s*:?\s*([^\n.;]+)",
        r"\btitle\s+(?:to\s+the\s+estate\s+or\s+interest\s+in\s+the\s+land\s+is\s+at\s+the\s+date\s+hereof\s+is\s+)?vested\s+in\s*:?\s*([^\n.;]+)",
        r"\btitle\s+(?:to\s+[^\n]+\s+)?vested\s+in\s*:?\s*\n\s*([^\n.;]+)",
        r"\bVesting\s*/\s*Ownership\s+([^\n.;]+)",
        r"\bRe:\s*([^\n,;]+?)\s+TS\s+No",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return _clean_owner(match.group(1))
    return "UNKNOWN OWNER"


def _clean_owner(value: str) -> str:
    value = re.split(r"\s*,\s*(?:a|an|as|the|husband|wife)\b", value, maxsplit=1, flags=re.I)[0]
    value = re.sub(r"\s+", " ", value).strip(" ,.;:")
    return value.upper() if value else "UNKNOWN OWNER"


def _extract_case_id(text: str) -> str:
    patterns = [
        r"\bTS\s*(?:No\.?|#)\s*[:#]?\s*([A-Z0-9\-]+)",
        r"\bCase\s*(?:No\.?|#)\s*[:#]?\s*([A-Z0-9\-]+(?:\s+[A-Z]{3})?)",
        r"\bInstrument\s*(?:No\.?|#)\s*[:#]?\s*([A-Z0-9\-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return _clean_value(match.group(1)).rstrip(".,;")
    return ""


def _extract_recorded_date(text: str) -> str:
    patterns = [
        r"\bRecorded\s+(?:on\s+)?([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
        r"\bPublished\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
        r"\bEffective\s+Date\s*[:\-]?\s*([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            parsed = _parse_date(match.group(1))
            if parsed:
                return parsed
    return ""


def _parse_date(value: str) -> str:
    value = value.strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _canonical_record(**values: str) -> dict[str, str]:
    row = {column: "" for column in CANONICAL_COLUMNS}
    row.update(
        {
            "owner": values.get("owner", ""),
            "property_address": values.get("property_address", ""),
            "parcel_id": values.get("parcel_id", ""),
            "signal": values.get("signal", ""),
            "source": "public legal notice",
            "source_url": values.get("source_url", ""),
            "recorded_date": values.get("recorded_date", ""),
            "case_id": values.get("case_id", ""),
            "notes": "Extracted from public legal notice text",
        }
    )
    return row


def _dedupe_records(records: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for row in records:
        key = (row.get("parcel_id", ""), row.get("signal", ""), row.get("case_id", ""), row.get("source_url", ""))
        deduped.setdefault(key, row)
    return list(deduped.values())


def _clean_value(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ,.;:\n\t")
