import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from shortlist_ml.ingest.sources import ParseError, parse_greenhouse, parse_lever


def test_greenhouse_fixture(fixtures_dir: Path) -> None:
    result = parse_greenhouse((fixtures_dir / "greenhouse.json").read_bytes())
    assert result.failed == 0 and len(result.postings) == 3
    ng, senior, ml1 = result.postings
    assert ng.external_id == "1001" and ng.source == "greenhouse"
    # Entity-escaped HTML is decoded and tags stripped; '&amp;amp;' ends up as a plain '&'.
    assert "Python & SQL" in ng.description_text and "<" not in ng.description_text
    assert (ng.city, ng.region, ng.country) == ("San Francisco", "CA", "US")
    assert ng.years_min == 0 and ng.seniority == "entry" and ng.is_entry_level
    assert ng.sponsorship == "restricted" and "visa sponsorship" in (ng.sponsorship_evidence or "")
    assert (ng.entry_evidence, ng.entry_evidence_text) == ("title_keyword", "New Grad")
    assert ng.url == ng.apply_url == "https://boards.example.test/acme/jobs/1001"
    # The live list endpoint does return first_published (the docs page does not show it).
    assert ng.source_posted_at == datetime(2026, 10, 1, 16, 0, tzinfo=UTC)  # 12:00-04:00
    assert ng.source_updated_at is not None
    assert senior.is_remote is True and senior.seniority == "senior"
    assert (
        ml1.sponsorship == "offered"
        and ml1.sponsorship_evidence is not None
        and ml1.seniority == "entry"
    )


def test_lever_fixture(fixtures_dir: Path) -> None:
    result = parse_lever((fixtures_dir / "lever.json").read_bytes())
    assert result.failed == 0 and len(result.postings) == 2
    grad, staff = result.postings
    assert grad.external_id == "a1b2c3d4-0001" and grad.apply_url.endswith("/apply")
    assert "Requirements" in grad.description_text and "- BS/MS in CS" in grad.description_text
    assert grad.years_min == 0 and grad.seniority == "entry"
    assert grad.source_posted_at is not None and grad.source_posted_at.year == 2025
    assert staff.is_remote is True and staff.seniority == "senior"
    assert staff.location_raw == "Remote; Toronto, ON, Canada"
    assert staff.apply_url == staff.url  # no applyUrl -> falls back to the hosted page
    assert (staff.sponsorship, staff.sponsorship_evidence) == (
        "unclear",
        None,
    )  # "We sponsor community events" is not visa sponsorship


def test_malformed_postings_are_counted_not_fatal() -> None:
    payload = {
        "jobs": [{"id": 1, "title": "ok", "absolute_url": "u", "content": ""}, {"id": 2}, "junk"]
    }
    result = parse_greenhouse(json.dumps(payload).encode())
    assert len(result.postings) == 1 and result.failed == 2


@pytest.mark.parametrize("parser", [parse_greenhouse, parse_lever])
@pytest.mark.parametrize("body", [b"not json", b'"a string"', b"{}", b"42"])
def test_wrong_top_level_shape_raises(parser, body: bytes) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ParseError):
        parser(body)


# ---- REAL recorded fixtures (data/fixtures/{greenhouse,lever}/sample.json)
def test_real_greenhouse_sample(real_fixtures_dir: Path) -> None:
    result = parse_greenhouse((real_fixtures_dir / "greenhouse" / "sample.json").read_bytes())
    assert result.failed == 0 and len(result.postings) == 3
    for p in result.postings:
        assert p.source_posted_at is not None and p.source_updated_at is not None
        assert p.url == p.apply_url and p.url.startswith("https://")
        assert (
            "<" not in p.description_text
            and "&lt;" not in p.description_text
            and len(p.description_text) > 500
        )
        assert p.country is None or (len(p.country) == 2 and p.country.isupper())
    early, director, intern = result.postings
    assert (
        early.seniority == "entry"
        and early.is_entry_level
        and early.country == "US"
        and early.region == "NY"
    )
    assert director.seniority == "senior" and director.is_remote is True
    assert intern.seniority == "intern" and not intern.is_entry_level


def test_real_lever_sample(real_fixtures_dir: Path) -> None:
    result = parse_lever((real_fixtures_dir / "lever" / "sample.json").read_bytes())
    assert result.failed == 0 and len(result.postings) == 3
    for p in result.postings:
        assert p.source_posted_at is not None  # createdAt is present on live Lever postings
        assert p.apply_url.startswith("https://") and p.url.startswith("https://")
        assert "<" not in p.description_text and len(p.description_text) > 500
        assert p.country is not None and len(p.country) == 2
