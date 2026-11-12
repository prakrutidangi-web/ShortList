import pytest

from shortlist_ml.ingest.normalize import (
    build_posting,
    classify_entry,
    classify_seniority,
    content_hash,
    detect_sponsorship,
    extract_years,
    extract_years_min,
    html_to_text,
    level_suffix,
    normalize_country,
    parse_location,
)


def test_html_to_text_structure_and_entities() -> None:
    html = (
        "<p>Hello &amp; welcome</p><ul><li>One</li><li>Two</li></ul><script>x()</script><p>End</p>"
    )
    assert html_to_text(html) == "Hello & welcome\n\n- One\n- Two\n\nEnd"


# ---------------------------------------------------------------- location
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("San Francisco, CA", ("San Francisco", "CA", "US", False)),
        ("New York, NY", ("New York", "NY", "US", False)),
        ("Remote - US", (None, None, "US", True)),
        ("Remote (US)", (None, None, "US", True)),
        ("Remote", (None, None, None, True)),
        ("Toronto, ON, Canada", ("Toronto", "ON", "CA", False)),
        ("Toronto, Ontario", ("Toronto", "ON", "CA", False)),
        ("London, United Kingdom", ("London", None, "GB", False)),
        ("Austin, TX; Remote", ("Austin", "TX", "US", True)),
        ("Austin, Texas", ("Austin", "TX", "US", False)),
        ("Washington, D.C.", ("Washington", "DC", "US", False)),
        ("New York, New York", ("New York", "NY", "US", False)),
        ("NY • United States", (None, "NY", "US", False)),
        ("CO - Hybrid", (None, "CO", "US", False)),
        ("New York City, NY - Hybrid", ("New York City", "NY", "US", False)),
        ("BC", (None, "BC", "CA", False)),
        ("USA", (None, None, "US", False)),
        ("Dublin, Ireland", ("Dublin", None, "IE", False)),
        ("Seattle", ("Seattle", None, None, False)),
        ("Washington", ("Washington", None, None, False)),  # ambiguous lone name: treated as a city
        (
            "San Francisco, CA | Seattle, WA",
            ("San Francisco", "CA", "US", False),
        ),  # first location only
        (
            "Austin, AMER",
            ("Austin", None, None, False),
        ),  # regions/unknown words never become a country
        ("Seattle, Travel-Required", ("Seattle", None, None, False)),
        # Cleanup rules added after the audit (junk tokens, suffixes, mixed lists):
        ("Remote - US: Select locations", (None, None, "US", True)),
        ("Remote - Canada: All locations", (None, None, "CA", True)),
        ("IN-Bengaluru", ("Bengaluru", None, "IN", False)),
        ("San Francisco, CA • New York, NY • United States", ("San Francisco", "CA", "US", False)),
        (
            "California, United States, Oregon, United States, Washington, United States",
            (None, "CA", "US", False),
        ),
        ("Washington DC metro area", ("Washington", "DC", "US", False)),
        (
            "Remote-Friendly (Travel-Required) | San Francisco, CA",
            ("San Francisco", "CA", "US", True),
        ),
        ("Hybrid - San Francisco, New York City, Austin", ("San Francisco", None, None, False)),
        (None, (None, None, None, None)),
        ("  ", (None, None, None, None)),
    ],
)
def test_parse_location(raw: str | None, expected: tuple[str | None, ...]) -> None:
    assert parse_location(raw) == expected


@pytest.mark.parametrize(
    "raw", ["Hybrid", "Distributed", "In-Office", "N/A", "Hybrid; In-Office", "Distributed; Hybrid"]
)
def test_no_place_means_everything_unknown_not_non_us(raw: str) -> None:
    """A work mode with no place leaves city/region/country NULL (unknown), never a guessed country."""
    city, region, country, _remote = parse_location(raw)
    assert (city, region, country) == (None, None, None)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("USA", "US"),
        ("United Kingdom", "GB"),
        ("UK", "GB"),
        ("gb", "GB"),
        ("Narnia", "Narnia"),
        (None, None),
        (" ", None),
    ],
)
def test_normalize_country(value: str | None, expected: str | None) -> None:
    assert normalize_country(value) == expected


# ---------------------------------------------------------------- years
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3+ years of professional experience", 3),
        ("0-2 years of experience with Python", 0),
        ("1 to 3 years' experience", 1),
        ("Minimum 5 years of relevant industry experience", 5),
        # max of the lower bounds: the strictest requirement is the headline one
        ("2+ years of backend experience; 5+ years of experience leading teams", 5),
        ("4+ years of professional Software Engineering experience; 2+ years of experience", 4),
        (
            "2\u201312+ years of industry software engineering experience",
            2,
        ),  # a range contributes its lower bound
        ("No experience needed", None),
        ("Founded 25 years ago, experience matters", None),
    ],
)
def test_extract_years(text: str, expected: int | None) -> None:
    assert extract_years_min(text) == expected


def test_extract_years_returns_the_matched_text() -> None:
    value, matched = extract_years(
        "We want 1+ years of experience, ideally 3+ years of experience."
    )
    assert value == 3 and matched == "3+ years of experience"


# ---------------------------------------------------------------- entry-level classification
@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Software Engineer, New Grad (2027)", None),
        ("Machine Learning Engineer I", 1),
        ("Software Engineer II", 2),
        ("Customer Support Specialist ll", 2),  # lowercase L's typed for II
        ("Data Engineer III", 3),
        ("Analyst 2", 2),
        ("Software Engineer II, Backend", 2),
        ("Software Engineer I, Early Career (London)", 1),
        ("Software Engineer", None),
        ("Phase I Clinical Lead", None),  # 'I' is not the last word
        ("I", None),
    ],
)
def test_level_suffix(title: str, expected: int | None) -> None:
    assert level_suffix(title) == expected


@pytest.mark.parametrize(
    ("title", "description", "years", "seniority", "entry", "rule"),
    [
        # title keyword
        ("Software Engineer, New Grad (2027)", "", None, "entry", True, "title_keyword"),
        ("Analyst, Early Career (Full Stack)", "", None, "entry", True, "title_keyword"),
        (
            "Junior Data Analyst",
            "needs 4+ years of experience",
            4,
            "entry",
            True,
            "title_keyword",
        ),  # title beats years
        ("Machine Learning Engineer I", "", None, "entry", True, "title_keyword"),
        ("Associate Product Manager", "", None, "entry", True, "title_keyword"),
        # contradictory / multi-level titles are NOT entry-level
        ("[Junior / Senior / Staff] Software Engineer", "", None, "unknown", False, None),
        ("Junior or Senior Engineer", "", None, "unknown", False, None),
        # senior / mid
        ("Senior Software Engineer", "", 0, "senior", False, None),
        ("Staff Machine Learning Engineer", "", None, "senior", False, None),
        (
            "Software Engineer II",
            "new grad welcome",
            None,
            "mid",
            False,
            None,
        ),  # level II beats a phrase
        ("Data Engineer III", "", None, "senior", False, None),
        # interns are not entry-level
        ("Software Engineering Intern", "new grad", None, "intern", False, None),
        # explicit phrase in the description
        ("Software Engineer", "We are hiring new grads this fall.", None, "entry", True, "phrase"),
        ("Software Engineer", "Open to the Class of 2027.", None, "entry", True, "phrase"),
        ("Software Engineer", "Join our early career program", 2, "entry", True, "phrase"),
        (
            "Software Engineer",
            "Early career program, but we need 4+ years of experience",
            4,
            "mid",
            False,
            None,
        ),
        (
            "Software Engineer",
            "Recent graduates and university graduates apply.",
            None,
            "entry",
            True,
            "phrase",
        ),
        # years rule: <= 1 only
        ("Data Engineer", "0-1 years of experience", 0, "entry", True, "years"),
        ("Data Engineer", "1+ years of experience", 1, "entry", True, "years"),
        ("Data Engineer", "2+ years of experience", 2, "mid", False, None),
        ("Data Engineer", "", 4, "mid", False, None),
        ("Data Engineer", "", 8, "senior", False, None),
        ("Data Engineer", "", None, "unknown", False, None),
    ],
)
def test_classify_entry(
    title: str, description: str, years: int | None, seniority: str, entry: bool, rule: str | None
) -> None:
    c = classify_entry(title, description, years)
    assert (c.seniority, c.is_entry_level, c.evidence) == (seniority, entry, rule)
    assert (c.evidence_text is not None) == entry  # evidence text is stored iff the flag is on


def test_years_evidence_text_is_the_matched_requirement() -> None:
    c = classify_entry("Data Engineer", "You have 1+ years of experience with SQL.", 1)
    assert c.evidence == "years" and c.evidence_text == "1+ years of experience"


def test_classify_seniority_wrapper_ignores_description_phrases() -> None:
    assert classify_seniority("Data Engineer", 1) == ("entry", True)
    assert classify_seniority("Data Engineer", 2) == ("mid", False)


# ---------------------------------------------------------------- sponsorship
@pytest.mark.parametrize(
    "text",
    [
        "We are unable to provide visa sponsorship for this role.",
        "We do not offer visa sponsorship at this time.",
        "No visa sponsorship is available.",
        "Sponsorship is not available for this position.",
        "Must be authorized to work in the United States without sponsorship.",
        "Candidates must be a U.S. citizen.",
        "This role cannot provide immigration sponsorship.",
        "This position is not eligible for immigration sponsorship.",
        "Work authorization: We do not sponsor visas for Fellows.",
        "We cannot sponsor H-1B visas for this role.",
        "Unfortunately we are unable to sponsor work visas.",
    ],
)
def test_sponsorship_restricted_with_evidence(text: str) -> None:
    value, evidence = detect_sponsorship("Intro. " + text + " Outro.")
    assert value == "restricted"
    assert evidence == text  # exactly the matched sentence, not its neighbours


@pytest.mark.parametrize(
    "text",
    [
        "We offer visa sponsorship for qualified candidates.",
        "Visa sponsorship is available.",
        "We sponsor H-1B visas for new graduates.",
        "We do sponsor visas for this team.",
    ],
)
def test_sponsorship_offered(text: str) -> None:
    value, evidence = detect_sponsorship("Intro. " + text + " Outro.")
    assert value == "offered" and evidence == text


@pytest.mark.parametrize(
    ("text", "snippet"),
    [
        # Anthropic wording
        (
            "Visa sponsorship: We do sponsor visas! However, we aren't able to successfully sponsor visas for every role and every candidate.",
            "every role and every candidate",
        ),
        # Roblox wording
        (
            "For US based roles only, please note the Company may not be able to employ candidates for this role who have United States work authorization related to certain U.S. visa categories, or support future H-1B sponsorship at this time.",
            "may not be able to employ candidates",
        ),
        (
            "Company sponsorship may be available for eligible candidates applying for certain roles.",
            "may be available",
        ),
        ("Visa sponsorship is handled on a case-by-case basis.", "case-by-case"),
    ],
)
def test_hedged_wording_is_unclear_with_the_snippet(text: str, snippet: str) -> None:
    value, evidence = detect_sponsorship(text)
    assert value == "unclear" and evidence is not None and snippet in evidence


@pytest.mark.parametrize(
    "text",
    [
        "",
        "We sponsor community events and hackathons.",
        "Our event sponsorship program funds student clubs.",
        "Candidates who do not require visa sponsorship are encouraged to apply.",  # ambiguous
        "Work authorization is required.",
        "You will work with the sponsor team on partnerships.",
        "Authorized to work in the US. We are an equal opportunity employer.",
        "Delivered under U.S. export laws without sponsorship for an export license.",
        "This role has strong executive sponsorship from the leadership team.",
    ],
)
def test_no_signal_is_unclear_without_evidence(text: str) -> None:
    assert detect_sponsorship(text) == ("unclear", None)


def test_contradictory_text_is_unclear_with_the_restriction_as_evidence() -> None:
    value, evidence = detect_sponsorship(
        "We offer visa sponsorship for some roles. We do not offer visa sponsorship for this one."
    )
    assert value == "unclear" and evidence == "We do not offer visa sponsorship for this one."


# ---------------------------------------------------------------- assembly
def test_content_hash_changes_with_content_only() -> None:
    base = content_hash("T", "SF", "desc")
    assert base == content_hash("T", "SF", "desc")
    assert base != content_hash("T", "SF", "desc2")
    assert base != content_hash("T2", "SF", "desc")
    assert base != content_hash("T", None, "desc")


def test_build_posting_remote_hint_country_hint_and_evidence() -> None:
    p = build_posting(
        source="lever",
        external_id="x",
        url="u",
        apply_url="a",
        title="Engineer II ",
        description_text="3+ years of experience. Visa sponsorship is available.",
        location_raw="Berlin",
        remote_hint=True,
        country_hint="DE",
    )
    assert p.title == "Engineer II"
    assert p.is_remote is True and p.country == "DE" and p.years_min == 3 and p.seniority == "mid"
    assert p.sponsorship == "offered" and p.sponsorship_evidence == "Visa sponsorship is available."
    assert p.entry_evidence is None and p.entry_evidence_text is None
