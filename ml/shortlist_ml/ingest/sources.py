"""Greenhouse and Lever payload parsers. Each turns one board response into NormalizedPostings."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
from typing import Any

from shortlist_ml.ingest.normalize import NormalizedPosting, build_posting, html_to_text


class ParseError(Exception):
    """The payload is not the expected top-level shape (board is unusable this run)."""


@dataclass(frozen=True)
class ParseResult:
    postings: list[NormalizedPosting]
    failed: int  # individual postings that could not be parsed (skipped, counted)


@dataclass(frozen=True)
class Source:
    name: str
    url: Callable[[str], str]
    parse: Callable[[bytes], ParseResult]


def _load(content: bytes) -> Any:
    try:
        return json.loads(content)
    except ValueError as exc:
        raise ParseError("invalid JSON") from exc


def _iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _ms(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


# ---------------------------------------------------------------- Greenhouse
def greenhouse_url(board_token: str, *, content: bool = True) -> str:
    base = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    return f"{base}?content=true" if content else base


def parse_greenhouse(content: bytes) -> ParseResult:
    data = _load(content)
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise ParseError("greenhouse: expected an object with a 'jobs' list")
    postings: list[NormalizedPosting] = []
    failed = 0
    for job in data["jobs"]:
        try:
            url = job["absolute_url"]
            # `content` is HTML that Greenhouse additionally entity-escapes; unescape then strip tags.
            description = html_to_text(unescape(job.get("content") or ""))
            postings.append(
                build_posting(
                    source="greenhouse",
                    external_id=str(job["id"]),
                    url=url,
                    apply_url=url,  # the company-hosted job page, which contains the application form
                    title=job["title"],
                    description_text=description,
                    location_raw=(job.get("location") or {}).get("name"),
                    source_posted_at=_iso(job.get("first_published")),
                    source_updated_at=_iso(job.get("updated_at")),
                )
            )
        except (KeyError, TypeError, AttributeError):
            failed += 1
    return ParseResult(postings, failed)


# ---------------------------------------------------------------- Lever
def lever_url(board_token: str) -> str:
    return f"https://api.lever.co/v0/postings/{board_token}?mode=json"


def _lever_description(job: dict[str, Any]) -> str:
    parts = [job.get("descriptionPlain") or html_to_text(job.get("description") or "")]
    for item in job.get("lists") or []:
        parts.append(f"{item.get('text', '')}\n{html_to_text(item.get('content') or '')}".strip())
    parts.append(job.get("additionalPlain") or html_to_text(job.get("additional") or ""))
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def parse_lever(content: bytes) -> ParseResult:
    data = _load(content)
    if not isinstance(data, list):
        raise ParseError("lever: expected a JSON list of postings")
    postings: list[NormalizedPosting] = []
    failed = 0
    for job in data:
        try:
            cats = job.get("categories") or {}
            locations = cats.get("allLocations") or (
                [cats["location"]] if cats.get("location") else []
            )
            hosted = job["hostedUrl"]
            postings.append(
                build_posting(
                    source="lever",
                    external_id=str(job["id"]),
                    url=hosted,
                    apply_url=job.get("applyUrl") or hosted,
                    title=job["text"],
                    description_text=_lever_description(job),
                    location_raw="; ".join(locations) or None,
                    remote_hint=True if job.get("workplaceType") == "remote" else None,
                    country_hint=job.get("country"),
                    source_posted_at=_ms(job.get("createdAt")),
                )
            )
        except (KeyError, TypeError, AttributeError):
            failed += 1
    return ParseResult(postings, failed)


SOURCES: dict[str, Source] = {
    "greenhouse": Source("greenhouse", greenhouse_url, parse_greenhouse),
    "lever": Source("lever", lever_url, parse_lever),
}
