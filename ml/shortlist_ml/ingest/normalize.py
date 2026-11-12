"""Rule-based posting normalization.

Everything here is a HEURISTIC with known failure modes (documented per function). Phase 2 adds
skill extraction and role family; a learned classifier may replace the seniority rules later.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser

SPONSORSHIP_VALUES = ("restricted", "offered", "unclear")
ENTRY_EVIDENCE_RULES = ("title_keyword", "phrase", "years")
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
    sponsorship_evidence: str | None
    entry_evidence: str | None
    entry_evidence_text: str | None
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
# Tokens that carry no place information; removed before parsing.
_JUNK_RE = re.compile(
    r"\b(?:n/a|na|distributed|metro area|remote[- ]friendly|travel[- ]required|multiple locations|anywhere)\b"
    r"|:\s*(?:select|all)\s+locations",
    re.I,
)
_ISO_PREFIX_RE = re.compile(r"^([A-Z]{2})-(.+)$")  # "IN-Bengaluru"
_KNOWN_ISO = frozenset(_COUNTRY_ALIASES.values())


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


def _parse_one(
    text: str, trailing_country: str | None
) -> tuple[str | None, str | None, str | None] | None:
    """Parse a single location; None if it has no place information at all."""
    text = _WORK_MODE_RE.sub(
        " ", _JUNK_RE.sub(" ", text)
    )  # junk first: "Remote-Friendly" is junk, not remote
    text = text.replace("(", ",").replace(")", ",")
    parts = [p.strip(" -\u2013") for p in text.split(",")]
    parts = [p for p in parts if p]
    if not parts:
        return None
    if len(parts) == 1 and parts[0].lower() in ("washington dc", "washington d.c.", "d.c."):
        return "Washington", "DC", "US"
    # Cut at the first country token: later parts are further locations ("..., United States, Oregon, ...").
    for i, part in enumerate(parts):
        if part.lower() in _COUNTRY_ALIASES:
            parts = parts[: i + 1]
            break
    city = region = None
    country = normalize_country(parts.pop()) if parts[-1].lower() in _COUNTRY_ALIASES else None
    if (
        len(parts) == 1
        and (m := _ISO_PREFIX_RE.match(parts[0]))
        and m.group(1) in _KNOWN_ISO
        and country is None
    ):
        country, parts = m.group(1), [m.group(2).strip()]
    if (
        parts
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
    country = country or trailing_country
    if city is None and region is None and country is None:
        return None
    return city, region, country


def parse_location(raw: str | None) -> tuple[str | None, str | None, str | None, bool | None]:
    """Return (city, region, country, is_remote); country is ISO alpha-2 where recognised and
    region is a US-state / Canadian-province abbreviation where recognised.

    UNKNOWN STAYS UNKNOWN: if the string carries no place ("Hybrid", "Distributed", "N/A") the result is
    (None, None, None, ...). A NULL country must never be read as "non-US" or used to drop a posting.

    Handles "City, ST", "City, State, Country", "ST \u2022 Country", "City, Country", "IN-Bengaluru",
    work-mode noise ("- Hybrid", "(Remote)"), junk tokens and ": Select locations" suffixes. Limitations:
    only the FIRST usable location of a multi-location string ("A; B", "A | B", "A or B", "A \u2022 B") is
    parsed (`location_raw` keeps all); a lone place name such as "Washington" is a city; there is no
    city->country gazetteer, so "San Francisco" alone has no country. is_remote is True if ANY location says
    remote, None if there is no location text at all.
    """
    if not raw or not raw.strip():
        return None, None, None, None
    is_remote = bool(_REMOTE_RE.search(raw))
    for chunk in re.split(r";|\s+\|\s+|\s+or\s+", raw):
        segs = [x for x in re.split(r"\s*\u2022\s*", chunk) if x.strip()]
        if not segs:
            continue
        trailing = None
        if len(segs) > 1 and segs[-1].strip().lower() in _COUNTRY_ALIASES:
            trailing = normalize_country(segs[-1])
        parsed = _parse_one(segs[0], trailing)
        if parsed is not None:
            return (*parsed, is_remote)
    return None, None, None, is_remote


# ---------------------------------------------------------------- years / seniority
_YEARS_RE = re.compile(
    r"(?<!\d)(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|\u2013|to)\s*(\d{1,2})\s*)?\+?\s*(?:years?|yrs?)\b"
    r"(?:['\u2019]s?)?(?:\s+of)?\s+(?:[a-z/,&-]+\s+){0,4}?(?:experience|exp)\b",
    re.I,
)


def extract_years(text: str) -> tuple[int | None, str | None]:
    """Headline experience requirement: the LARGEST lower bound among all 'N years ... experience'
    mentions, with the matched text. ('4+ years ... 2+ years' -> 4; '0-2 years' -> 0; a range
    '2-12+ years' contributes its lower bound 2.)

    Why max: postings list several requirements and the strictest one is what decides whether a new
    grad can apply. (The first version took the minimum; an audit showed that picked the weakest
    requirement.) Misses phrasings like 'experience: 3 years'. Values above 20 are ignored.
    """
    best: tuple[int, str] | None = None
    for m in _YEARS_RE.finditer(text):
        val = int(m.group(1))
        if val <= 20 and (best is None or val > best[0]):
            best = (val, m.group(0))
    return (best[0], best[1]) if best else (None, None)


def extract_years_min(text: str) -> int | None:
    return extract_years(text)[0]


_INTERN_RE = re.compile(r"\b(intern|internship|co-?op)\b", re.I)
_ENTRY_TITLE_RE = re.compile(
    r"\b(new[- ]?grad(?:uate)?s?|university grad(?:uate)?s?|recent grad(?:uate)?s?|early[- ]career|"
    r"entry[- ]level|junior|jr\.?|graduate|apprentice|associate product manager|apm)\b",
    re.I,
)
# Explicit early-career wording in the DESCRIPTION. Kept narrow on purpose; recorded as its own
# evidence type ('phrase') so downstream code can weigh it differently from a title keyword.
_ENTRY_PHRASE_RE = re.compile(
    r"\b(new[- ]?grad(?:uate)?s?|university[- ]grad(?:uate)?s?|recent[- ]grad(?:uate)?s?|"
    r"early[- ]career|class of 20\d\d)\b",
    re.I,
)
_SENIOR_RE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|director|head of|vp|vice president|architect|"
    r"distinguished|fellow|manager)\b",
    re.I,
)
_LEVEL_SUFFIX_RE = re.compile(r"^(?P<base>.*\S)\s+(?P<lvl>iv|iii|ii|i|ll|lll|1|2|3|4)$", re.I)
_LEVELS = {"i": 1, "1": 1, "ii": 2, "ll": 2, "2": 2, "iii": 3, "lll": 3, "3": 3, "iv": 4, "4": 4}


def level_suffix(title: str) -> int | None:
    """Level number from a trailing suffix such as 'Engineer I', 'Specialist II', 'Analyst 3', in the
    title or in any comma segment ('Software Engineer II, Backend'). Parenthetical text is ignored.
    'll' / 'lll' (lowercase L's typed for II/III) are accepted."""
    stripped = re.sub(r"\([^)]*\)", " ", title)
    for segment in (seg.strip() for seg in stripped.split(",")):
        m = _LEVEL_SUFFIX_RE.match(segment)
        if m and len(m.group("base").split()) >= 1:
            return _LEVELS[m.group("lvl").lower()]
    return None


@dataclass(frozen=True)
class EntryClassification:
    seniority: str
    is_entry_level: bool
    evidence: str | None  # 'title_keyword' | 'phrase' | 'years' (only when is_entry_level)
    evidence_text: str | None


def classify_entry(title: str, description_text: str, years_min: int | None) -> EntryClassification:
    """Seniority bucket plus WHY a posting was called entry-level. A soft signal, never a gate.

    Order: intern -> contradictory title (entry AND senior keywords, e.g. '[Junior / Senior / Staff]'
    -> unknown) -> title entry keyword or level 'I' -> title senior keyword -> level II (mid) / III+
    (senior) -> explicit early-career phrase in the description (only if years_min is absent or <= 2)
    -> years rule (years_min <= 1 -> entry, 2-5 mid, >= 6 senior) -> unknown.
    Interns are not marked entry-level (the target is full-time new-grad roles).
    """
    none = EntryClassification
    if _INTERN_RE.search(title):
        return none("intern", False, None, None)
    level = level_suffix(title)
    entry_m = _ENTRY_TITLE_RE.search(title)
    # Judge "senior" on the title WITHOUT the entry phrase, so 'Associate Product Manager' is not
    # contradicted by its own word 'Manager'.
    rest = title[: entry_m.start()] + " " + title[entry_m.end() :] if entry_m else title
    senior = _SENIOR_RE.search(rest)
    if (entry_m or level == 1) and senior:
        return none("unknown", False, None, None)
    if entry_m:
        return none("entry", True, "title_keyword", entry_m.group(0))
    if level == 1:
        return none("entry", True, "title_keyword", f"level {level} suffix in title")
    if senior:
        return none("senior", False, None, None)
    if level is not None:
        return none("mid" if level == 2 else "senior", False, None, None)
    phrase = _ENTRY_PHRASE_RE.search(description_text)
    if phrase and (years_min is None or years_min <= 2):
        return none("entry", True, "phrase", phrase.group(0))
    if years_min is not None:
        if years_min <= 1:
            _, text = extract_years(description_text)
            return none("entry", True, "years", text)
        return none("mid" if years_min <= 5 else "senior", False, None, None)
    return none("unknown", False, None, None)


def classify_seniority(title: str, years_min: int | None) -> tuple[str, bool]:
    """Title/years-only view (no description phrases), kept for simple callers and tests."""
    c = classify_entry(title, "", years_min)
    return c.seniority, c.is_entry_level


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
    # Verb form: "we do not sponsor visas", "cannot sponsor H-1B". Added after a population scan showed
    # "We do not sponsor visas for Fellows." labelled 'offered'.
    re.compile(
        r"\b(?:do(?:es)?\s+not|don't|doesn't|cannot|can't|can\s+not|will\s+not|won't|unable\s+to|"
        r"not\s+able\s+to|are\s+not\s+able\s+to)\s+(?:currently\s+|presently\s+)?sponsor\b[^.]{0,40}?"
        r"\b(?:visas?|h-?1b|work|employment|immigration)",
        re.I,
    ),
]
# Hedged wording: the company says it MAY be unable / only sometimes able. Reported as 'unclear' with the sentence.
_HEDGED_PATTERNS = [
    re.compile(
        r"\bmay\s+not\s+be\s+able\s+to\s+(?:employ|sponsor|hire|offer|provide|support)\b[^.]{0,200}?"
        r"(?:visa|h-?1b|sponsorship|work\s+authori[sz]ation)",
        re.I,
    ),
    re.compile(
        r"\b(?:aren'?t|are\s+not|isn'?t|is\s+not|not|unable\s+to)\s+(?:be\s+)?(?:able\s+to\s+)?(?:successfully\s+)?"
        r"(?:sponsor|provide|offer)\b[^.]{0,80}?\b(?:every|all|any)\s+(?:role|candidate|position)",
        re.I,
    ),
    re.compile(
        r"\bsponsorship\s+(?:may|might)\s+(?:or\s+may\s+not\s+)?be\s+(?:available|offered|provided)",
        re.I,
    ),
    re.compile(
        r"\b(?:case[- ]by[- ]case|limited)\b[^.]{0,40}\b(?:visa\s+)?sponsorship|\bsponsorship\b[^.]{0,40}\bcase[- ]by[- ]case",
        re.I,
    ),
]
# "authorized to work ... without sponsorship": only counts with an authorization phrase before it.
_WITHOUT_SPONSORSHIP = re.compile(
    r"\bwithout\s+(?:the\s+need\s+for\s+)?(?:current\s+or\s+future\s+)?(?:(?:visa|employer|immigration)\s+)?sponsorship",
    re.I,
)
_AUTH_BEFORE = re.compile(r"(?:authori[sz]ed|eligible|legally|right)\s+to\s+work", re.I)
_OFFERED_PATTERNS = [
    re.compile(
        rf"\b(?:offer|provide|support)s?\s+(?:\w+\s+){{0,2}}?{_V}(?:\s+visa)?\s+sponsorship", re.I
    ),
    re.compile(
        rf"\b{_V}(?:\s+visa)?\s+sponsorship\s+(?:is\s+|are\s+)?(?:available|offered|provided)", re.I
    ),
    re.compile(r"\bsponsor(?:s|ing)?\s+(?:\w+\s+){0,2}?(?:visas?|h-?1b)\b", re.I),
]
_NEED_VERBS = re.compile(r"\b(?:require|requires|need|needs)\b", re.I)
_EVIDENCE_CAP = 300


def _sentence(flat: str, start: int, end: int) -> str:
    """The sentence of `flat` containing [start, end), capped to ~300 chars around the match."""
    a = max((flat.rfind(sep, 0, start) + len(sep) for sep in (". ", "! ", "? ")), default=0)
    ends = [i for i in (flat.find(sep, end) for sep in (". ", "! ", "? ")) if i != -1]
    b = (min(ends) + 1) if ends else len(flat)
    a = max(a, 0)
    if b - a > _EVIDENCE_CAP:
        a, b = max(a, start - 120), min(b, end + 120)
    return flat[a:b].strip()


def detect_sponsorship(text: str) -> tuple[str, str | None]:
    """Work-authorization signal: (value, evidence sentence).

    value is 'restricted' (explicit: no sponsorship / citizens only), 'offered' (explicit offer) or
    'unclear'. 'unclear' covers both "not mentioned" (evidence None) and hedged or contradictory
    wording (evidence = the sentence, e.g. "we may not be able to ... H-1B sponsorship at this
    time", "we do sponsor visas, however not for every role"). It is a UI WARNING only, never a filter.
    Unrelated uses of the word (executive/event sponsorship) and "do not require sponsorship are
    welcome" wording are deliberately not matched.
    """
    flat = re.sub(r"\s+", " ", text)
    for pat in _HEDGED_PATTERNS:
        if m := pat.search(flat):
            return "unclear", _sentence(flat, *m.span())

    spans: list[tuple[int, int]] = []
    for pat in _RESTRICTED_PATTERNS:
        for m in pat.finditer(flat):
            if not _NEED_VERBS.search(m.group(0)):
                spans.append(m.span())
    for m in _WITHOUT_SPONSORSHIP.finditer(flat):
        if _AUTH_BEFORE.search(flat[max(0, m.start() - 150) : m.start()]):
            spans.append(m.span())

    remainder = flat
    for start, end in sorted(
        spans, reverse=True
    ):  # blank restricted spans so "do not offer ..." isn't an offer
        remainder = remainder[:start] + " " * (end - start) + remainder[end:]
    offered = next((m for p in _OFFERED_PATTERNS if (m := p.search(remainder))), None)

    if spans and not offered:
        return "restricted", _sentence(flat, *min(spans))
    if offered and not spans:
        return "offered", _sentence(flat, *offered.span())
    if spans and offered:  # contradictory: report the restriction sentence as the evidence
        return "unclear", _sentence(flat, *min(spans))
    return "unclear", None


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
    entry_evidence: str | None
    entry_evidence_text: str | None
    sponsorship: str
    sponsorship_evidence: str | None


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
    c = classify_entry(title, description_text, years)
    sponsorship, sponsorship_evidence = detect_sponsorship(description_text)
    return Derived(
        city, region, country, is_remote, years, c.seniority, c.is_entry_level,
        c.evidence, c.evidence_text, sponsorship, sponsorship_evidence,
    )  # fmt: skip


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
        sponsorship_evidence=d.sponsorship_evidence,
        entry_evidence=d.entry_evidence,
        entry_evidence_text=d.entry_evidence_text,
        source_posted_at=source_posted_at,
        source_updated_at=source_updated_at,
        content_hash=content_hash(title, location_raw, description_text),
    )
