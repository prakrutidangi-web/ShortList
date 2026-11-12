"""Rule-based posting normalization.

Everything here is a HEURISTIC with known failure modes (documented per function). Phase 2 adds
skill extraction and role family; a learned classifier may replace the seniority rules later.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser

SPONSORSHIP_VALUES = ("restricted", "sponsors", "unknown")
SENIORITY_VALUES = ("intern", "entry", "mid", "senior", "unknown")


@dataclass(frozen=True)
class NormalizedPosting:
    source: str
    external_id: str
    url: str
    apply_url: str
    title: str
    description_text: str
    location_raw: str | None
    city: str | None
    region: str | None
    country: str | None
    is_remote: bool | None
    years_min: int | None
    seniority: str
    is_entry_level: bool
    sponsorship: str
    source_posted_at: datetime | None
    source_updated_at: datetime | None
    content_hash: str


# ---------------------------------------------------------------- HTML -> text
_BLOCK_TAGS = {"p", "br", "div", "li", "ul", "ol", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n- " if tag == "li" else "\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        elif (
            tag in _BLOCK_TAGS and tag != "li"
        ):  # list items start their own line; keep lists tight
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    lines = (
        re.sub(r"[ \t\u00a0]+", " ", line).strip() for line in "".join(parser.parts).split("\n")
    )
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):  # collapse runs of blank lines to one
            out.append(line)
    return "\n".join(out).strip()


# ---------------------------------------------------------------- location
_US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}  # fmt: skip
_CA_PROVINCES = {
    "AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba", "NB": "New Brunswick",
    "NL": "Newfoundland and Labrador", "NS": "Nova Scotia", "ON": "Ontario",
    "PE": "Prince Edward Island", "QC": "Quebec", "SK": "Saskatchewan",
}  # fmt: skip
_STATE_BY_NAME = {n.lower(): a for a, n in _US_STATES.items()} | {
    "d.c.": "DC",
    "washington dc": "DC",
}
_PROVINCE_BY_NAME = {n.lower(): a for a, n in _CA_PROVINCES.items()} | {"québec": "QC"}
_COUNTRY_ALIASES = {
    "us": "US", "usa": "US", "u.s.": "US", "u.s.a.": "US", "united states": "US",
    "united states of america": "US", "uk": "GB", "u.k.": "GB", "united kingdom": "GB",
    "great britain": "GB", "england": "GB", "canada": "CA", "india": "IN", "japan": "JP",
    "ireland": "IE", "germany": "DE", "australia": "AU", "france": "FR", "south korea": "KR",
    "korea": "KR", "brazil": "BR", "netherlands": "NL", "the netherlands": "NL",
    "singapore": "SG", "mexico": "MX", "spain": "ES", "poland": "PL", "israel": "IL",
    "sweden": "SE", "switzerland": "CH", "italy": "IT", "china": "CN", "argentina": "AR",
    "colombia": "CO", "philippines": "PH", "united arab emirates": "AE", "uae": "AE",
    "taiwan": "TW", "hong kong": "HK", "new zealand": "NZ", "portugal": "PT", "denmark": "DK",
    "norway": "NO", "finland": "FI", "belgium": "BE", "austria": "AT", "czech republic": "CZ",
    "czechia": "CZ", "romania": "RO", "vietnam": "VN", "indonesia": "ID", "chile": "CL",
    "costa rica": "CR", "turkey": "TR", "ukraine": "UA", "south africa": "ZA", "nigeria": "NG",
    "kenya": "KE", "egypt": "EG", "saudi arabia": "SA", "lithuania": "LT", "estonia": "EE",
    "bulgaria": "BG", "serbia": "RS", "greece": "GR", "hungary": "HU", "malaysia": "MY",
    "thailand": "TH", "pakistan": "PK", "bangladesh": "BD", "peru": "PE", "uruguay": "UY",
}  # fmt: skip
_REMOTE_RE = re.compile(r"\bremote\b", re.I)
_WORK_MODE_RE = re.compile(r"[\s(\-\u2013]*\b(?:remote|hybrid|on-?site|in[- ]office)\b[)\s]*", re.I)


def normalize_country(value: str | None) -> str | None:
    """Map names/aliases to ISO-3166 alpha-2 ('USA' -> 'US', 'United Kingdom' -> 'GB'). A bare
    2-letter code passes through uppercased; anything unrecognised is returned as given."""
    if not value or not value.strip():
        return None
    v = value.strip()
    if v.lower() in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[v.lower()]
    return v.upper() if re.fullmatch(r"[A-Za-z]{2}", v) else v


def _as_region(part: str) -> tuple[str, str] | None:
    """If `part` is a US state / DC / Canadian province (abbreviation or name) return (abbr, country)."""
    key = part.strip().rstrip(".").upper() if len(part.strip().rstrip(".")) == 2 else None
    low = part.strip().lower()
    if key in _US_STATES:
        return key, "US"
    if key in _CA_PROVINCES:
        return key, "CA"
    if low in _STATE_BY_NAME:
        return _STATE_BY_NAME[low], "US"
    if low in _PROVINCE_BY_NAME:
        return _PROVINCE_BY_NAME[low], "CA"
    return None


def parse_location(raw: str | None) -> tuple[str | None, str | None, str | None, bool | None]:
    """Return (city, region, country, is_remote); country is ISO alpha-2 where recognised and
    region is a US-state / Canadian-province abbreviation where recognised.

    Handles "City, ST", "City, State, Country", "ST • Country", "City, Country", work-mode noise
    ("- Hybrid", "(Remote)"). Limitations: only the FIRST location of a multi-location string
    ("A; B", "A | B", "A or B") is parsed (`location_raw` keeps all); unrecognised region names
    outside the US/Canada are ignored (the country stays None unless it is recognised); a lone place name such
    as "Washington" is treated as a city. is_remote is True if ANY location says remote, None if
    there is no location text.
    """
    if not raw or not raw.strip():
        return None, None, None, None
    is_remote = bool(_REMOTE_RE.search(raw))
    first = re.split(r";|\s+\|\s+|\s+or\s+", raw)[0]
    first = _WORK_MODE_RE.sub(" ", first)
    first = first.replace("\u2022", ",").replace("(", ",").replace(")", ",")
    parts = [p.strip(" -\u2013") for p in first.split(",")]
    parts = [p for p in parts if p]
    city = region = country = None
    if parts and parts[-1].lower() in _COUNTRY_ALIASES:  # trailing country
        country = normalize_country(parts.pop())
    if (
        parts
        and len(parts) >= 1
        and (hit := _as_region(parts[-1]))
        and (len(parts) > 1 or len(parts[-1].strip()) == 2 or country)
    ):
        region, region_country = hit
        country = country or region_country
        parts.pop()
    if parts:
        city = parts[0]
        tail = parts[-1] if len(parts) >= 2 else ""
        if country is None and (
            tail.lower() in _COUNTRY_ALIASES or re.fullmatch(r"[A-Z]{2}", tail)
        ):
            country = normalize_country(tail)  # only recognised countries; never free text
    return city, region, country, is_remote


# ---------------------------------------------------------------- years / seniority
_YEARS_RE = re.compile(
    r"(?<!\d)(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|\u2013|to)\s*(\d{1,2})\s*)?\+?\s*(?:years?|yrs?)\b"
    r"(?:['\u2019]s?)?(?:\s+of)?\s+(?:[a-z/,&-]+\s+){0,4}?(?:experience|exp)\b",
    re.I,
)


def extract_years_min(text: str) -> int | None:
    """Smallest 'N years ... experience' figure mentioned (so '0-2 years' -> 0, '3+ years' -> 3).

    Heuristic: if a posting lists several requirements we take the minimum, which errs toward
    keeping borderline postings visible. Misses phrasings like 'experience: 3 years'.
    """
    vals = [int(m.group(1)) for m in _YEARS_RE.finditer(text) if int(m.group(1)) <= 20]
    return min(vals) if vals else None


_INTERN_RE = re.compile(r"\b(intern|internship|co-?op)\b", re.I)
_ENTRY_RE = re.compile(
    r"\b(new[- ]?grad(?:uate)?s?|university grad(?:uate)?s?|recent grad(?:uate)?s?|early[- ]career|"
    r"entry[- ]level|junior|jr\.?|graduate|apprentice|associate product manager|apm)\b"
    r"|\b(?:engineer|developer|scientist|analyst)\s+(?:i|1)\b(?!\w)",
    re.I,
)
_SENIOR_RE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|director|head of|vp|vice president|architect|"
    r"distinguished|fellow|manager)\b",
    re.I,
)
_MID_RE = re.compile(r"\b(?:engineer|developer|scientist|analyst)\s+(?:ii|2)\b(?!\w)", re.I)


def classify_seniority(title: str, years_min: int | None) -> tuple[str, bool]:
    """Return (seniority, is_entry_level). Title keywords win over years.

    Order: intern -> explicit entry keywords -> senior keywords -> years. Interns are NOT marked
    is_entry_level (the target is full-time new-grad roles). Known failure modes: 'Lead' or
    'Manager' in non-seniority senses, titles with no level signal fall to 'unknown'.
    """
    if _INTERN_RE.search(title):
        return "intern", False
    if _ENTRY_RE.search(title):
        return "entry", True
    if _SENIOR_RE.search(title):
        return "senior", False
    if _MID_RE.search(title):
        return "mid", False
    if years_min is not None:
        if years_min <= 2:
            return "entry", True
        if years_min <= 5:
            return "mid", False
        return "senior", False
    return "unknown", False


# ---------------------------------------------------------------- sponsorship
_V = r"(?:visa|immigration|work(?:\s+authori[sz]ation)?|employment|employer)"
_RESTRICTED_PATTERNS = [
    # "no visa sponsorship", "unable to provide immigration sponsorship", "do not offer work visa sponsorship"
    re.compile(
        r"\b(?:no|not\s+(?:able|available|eligible)|unable|cannot|can't|won't|will\s+not|"
        rf"do(?:es)?\s+not|don't|doesn't)\b[^.\n]{{0,50}}?\b{_V}(?:\s+visa)?\s+sponsorship",
        re.I,
    ),
    re.compile(
        r"\bsponsorship\s+(?:is\s+)?(?:not\s+(?:available|offered|provided)|unavailable)", re.I
    ),
    re.compile(
        r"\b(?:must|need\s+to|required\s+to)\s+be\s+(?:a\s+)?(?:u\.?s\.?|united\s+states)\s+citizen",
        re.I,
    ),
    re.compile(r"\b(?:u\.?s\.?|united\s+states)\s+citizens?\s+(?:only|required)", re.I),
]
# "authorized to work ... without sponsorship": only counts with an authorization phrase before it.
_WITHOUT_SPONSORSHIP = re.compile(
    r"\bwithout\s+(?:the\s+need\s+for\s+)?(?:current\s+or\s+future\s+)?(?:(?:visa|employer|immigration)\s+)?sponsorship",
    re.I,
)
_AUTH_BEFORE = re.compile(r"(?:authori[sz]ed|eligible|legally|right)\s+to\s+work", re.I)
_SPONSORS_PATTERNS = [
    re.compile(
        rf"\b(?:offer|provide|support)s?\s+(?:\w+\s+){{0,2}}?{_V}(?:\s+visa)?\s+sponsorship", re.I
    ),
    re.compile(
        rf"\b{_V}(?:\s+visa)?\s+sponsorship\s+(?:is\s+|are\s+)?(?:available|offered|provided)", re.I
    ),
    re.compile(r"\bsponsor(?:s|ing)?\s+(?:\w+\s+){0,2}?(?:visas?|h-?1b)\b", re.I),
]
_NEED_VERBS = re.compile(r"\b(?:require|requires|need|needs)\b", re.I)


def detect_sponsorship(text: str) -> str:
    """Conservative, rule-based work-authorization signal: restricted | sponsors | unknown.

    Used as a UI WARNING only, never to filter. When in doubt it returns 'unknown': statements
    like "candidates who do not require sponsorship are welcome" (ambiguous), unrelated uses of
    'sponsor' (events, teams), or text containing both a restriction and an offer.
    """
    flat = re.sub(r"\s+", " ", text)
    spans: list[tuple[int, int]] = []
    for pat in _RESTRICTED_PATTERNS:
        for m in pat.finditer(flat):
            if not _NEED_VERBS.search(m.group(0)):
                spans.append(m.span())
    for m in _WITHOUT_SPONSORSHIP.finditer(flat):
        if _AUTH_BEFORE.search(flat[max(0, m.start() - 150) : m.start()]):
            spans.append(m.span())
    restricted = bool(spans)

    remainder = flat
    for start, end in sorted(
        spans, reverse=True
    ):  # blank restricted spans so "do not offer ..." isn't an offer
        remainder = remainder[:start] + " " * (end - start) + remainder[end:]
    sponsors = any(p.search(remainder) for p in _SPONSORS_PATTERNS)

    if restricted and not sponsors:
        return "restricted"
    if sponsors and not restricted:
        return "sponsors"
    return "unknown"


# ---------------------------------------------------------------- assembly
def content_hash(title: str, location_raw: str | None, description_text: str) -> str:
    """Hash of the user-visible content; a change means the posting was EDITED (not reposted)."""
    payload = "\x1f".join([title, location_raw or "", description_text])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Derived:
    city: str | None
    region: str | None
    country: str | None
    is_remote: bool | None
    years_min: int | None
    seniority: str
    is_entry_level: bool
    sponsorship: str


def derive_fields(
    title: str,
    description_text: str,
    location_raw: str | None,
    *,
    remote_hint: bool | None = None,
    country_hint: str | None = None,
) -> Derived:
    """Everything computed by rules from the posting text. Re-runnable on stored rows (`reparse`)."""
    city, region, country, is_remote = parse_location(location_raw)
    if remote_hint is not None:
        is_remote = remote_hint or is_remote
    country = country or normalize_country(country_hint)
    years = extract_years_min(description_text)
    seniority, entry = classify_seniority(title, years)
    return Derived(
        city,
        region,
        country,
        is_remote,
        years,
        seniority,
        entry,
        detect_sponsorship(description_text),
    )


def build_posting(
    *,
    source: str,
    external_id: str,
    url: str,
    apply_url: str,
    title: str,
    description_text: str,
    location_raw: str | None,
    remote_hint: bool | None = None,
    country_hint: str | None = None,
    source_posted_at: datetime | None = None,
    source_updated_at: datetime | None = None,
) -> NormalizedPosting:
    title = re.sub(r"\s+", " ", title).strip()
    d = derive_fields(
        title, description_text, location_raw, remote_hint=remote_hint, country_hint=country_hint
    )
    return NormalizedPosting(
        source=source,
        external_id=external_id,
        url=url,
        apply_url=apply_url,
        title=title,
        description_text=description_text,
        location_raw=location_raw,
        city=d.city,
        region=d.region,
        country=d.country,
        is_remote=d.is_remote,
        years_min=d.years_min,
        seniority=d.seniority,
        is_entry_level=d.is_entry_level,
        sponsorship=d.sponsorship,
        source_posted_at=source_posted_at,
        source_updated_at=source_updated_at,
        content_hash=content_hash(title, location_raw, description_text),
    )
