import pytest

from shortlist_ml.ingest.normalize import (
    build_posting,
    classify_seniority,
    content_hash,
    detect_sponsorship,
    extract_years_min,
    html_to_text,
    normalize_country,
    parse_location,
)


def test_html_to_text_structure_and_entities() -> None:
    html = (
        "<p>Hello &amp; welcome</p><ul><li>One</li><li>Two</li></ul><script>x()</script><p>End</p>"
    )
    assert html_to_text(html) == "Hello & welcome\n\n- One\n- Two\n\nEnd"


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
        # Real-world strings that the first version got wrong (country came out as 'Texas', 'D.C.', ...):
        ("Austin, Texas", ("Austin", "TX", "US", False)),
        ("Washington, D.C.", ("Washington", "DC", "US", False)),
        ("New York, New York", ("New York", "NY", "US", False)),
        ("NY \u2022 United States", (None, "NY", "US", False)),
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
        (None, (None, None, None, None)),
        ("  ", (None, None, None, None)),
    ],
)
def test_parse_location(raw: str | None, expected: tuple[str | None, ...]) -> None:
    assert parse_location(raw) == expected


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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3+ years of professional experience", 3),
        ("0-2 years of experience with Python", 0),
        ("1 to 3 years' experience", 1),
        ("Minimum 5 years of relevant industry experience", 5),
        ("2+ years of backend experience; 5+ years of experience leading teams", 2),
        ("No experience needed", None),
        ("Founded 25 years ago, experience matters", None),
    ],
)
def test_extract_years_min(text: str, expected: int | None) -> None:
    assert extract_years_min(text) == expected


@pytest.mark.parametrize(
    ("title", "years", "expected"),
    [
        ("Software Engineer, New Grad (2027)", None, ("entry", True)),
        ("Machine Learning Engineer I", None, ("entry", True)),
        ("Junior Data Analyst", 4, ("entry", True)),  # title keyword beats years
        ("Software Engineering Intern", None, ("intern", False)),
        ("Senior Software Engineer", 0, ("senior", False)),  # senior title beats years
        ("Staff Machine Learning Engineer", None, ("senior", False)),
        ("Software Engineer II", None, ("mid", False)),
        ("Data Engineer", 1, ("entry", True)),
        ("Data Engineer", 4, ("mid", False)),
        ("Data Engineer", 8, ("senior", False)),
        ("Data Engineer", None, ("unknown", False)),
        ("Associate Product Manager", None, ("entry", True)),
    ],
)
def test_classify_seniority(title: str, years: int | None, expected: tuple[str, bool]) -> None:
    assert classify_seniority(title, years) == expected


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
    ],
)
def test_sponsorship_restricted(text: str) -> None:
    assert detect_sponsorship(text) == "restricted"


@pytest.mark.parametrize(
    "text",
    [
        "We offer visa sponsorship for qualified candidates.",
        "Visa sponsorship is available.",
        "We sponsor H-1B visas for new graduates.",
    ],
)
def test_sponsorship_sponsors(text: str) -> None:
    assert detect_sponsorship(text) == "sponsors"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "We sponsor community events and hackathons.",
        "Our event sponsorship program funds student clubs.",
        "Candidates who do not require visa sponsorship are encouraged to apply.",  # ambiguous
        "Work authorization is required.",  # requires authorization, says nothing about sponsorship
        "You will work with the sponsor team on partnerships.",
        # Contradictory text must not be called either way:
        "We offer visa sponsorship for some roles. We do not offer visa sponsorship for this one.",
        "Authorized to work in the US. We are an equal opportunity employer.",
    ],
)
def test_sponsorship_unknown_when_unsure(text: str) -> None:
    assert detect_sponsorship(text) == "unknown"


def test_content_hash_changes_with_content_only() -> None:
    base = content_hash("T", "SF", "desc")
    assert base == content_hash("T", "SF", "desc")
    assert base != content_hash("T", "SF", "desc2")
    assert base != content_hash("T2", "SF", "desc")
    assert base != content_hash("T", None, "desc")


def test_build_posting_remote_hint_and_country_hint() -> None:
    p = build_posting(
        source="lever", external_id="x", url="u", apply_url="a", title="Engineer  II ",
        description_text="3+ years of experience", location_raw="Berlin", remote_hint=True,
        country_hint="DE",
    )  # fmt: skip
    assert p.title == "Engineer II"
    assert p.is_remote is True and p.country == "DE" and p.years_min == 3 and p.seniority == "mid"
