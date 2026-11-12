"""Stage 1 retrieval (exact cosine over posting embeddings) + a HAND-WEIGHTED content-based scorer.

!!! The weights below are an a-priori guess and are UNTUNED. Nothing here has been shown to beat any
baseline: Phase 3 builds the evaluation (recency-only, cosine-only, BM25) and Phase 4 replaces this
scorer with a learned ranker. Do not describe this ranking as "better" than anything yet. !!!

Recency limitation: every posting from the first ingest shares the same `first_seen_at`, so a
first_seen_at-based recency would be meaningless today. Recency therefore uses the company-reported
date (`source_posted_at`: Greenhouse first_published / Lever createdAt, present on 100% of postings so
far), capped at one year. Those dates can be stale (evergreen or refreshed listings). Once the daily
ingest has run for a few weeks, "new to us" (first_seen_at) can be added as a separate feature.
"""

import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Float, func, or_, select
from sqlalchemy.orm import Session

from shortlist_ml.db.models import Company, Posting, PostingEmbedding, PostingSkill, UserProfile

WEIGHTS_VERSION = "untuned-v0"
WEIGHTS = {  # sum to 1.0. UNTUNED a-priori guesses, not fitted to anything.
    "cosine": 0.45,
    "skill_coverage": 0.20,
    "seniority_fit": 0.15,
    "location_fit": 0.10,
    "recency": 0.10,
}
RECENCY_TAU_DAYS = 60.0  # untuned
RECENCY_CAP_DAYS = (
    365  # older company-reported dates are treated as 365 days old (possible evergreen listing)
)
SENIORITY_FIT = {"entry": 1.0, "unknown": 0.6, "mid": 0.4, "senior": 0.05}
INTERN_FIT_WHEN_SHOWN = 0.7
NEUTRAL = 0.5  # used when a component cannot be computed (never a penalty)
CANDIDATES_K = 200
POOL_CAP = CANDIDATES_K * 3  # rows fetched by similarity before repost/variant collapsing


@dataclass
class Filters:
    location_query: str | None = None
    remote_only: bool = False
    role_families: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    posted_within_days: int | None = None
    include_interns: bool = False
    entry_only: bool = False
    hide_restricted_sponsorship: bool = False
    collapse_variants: bool = True
    limit: int = 20
    offset: int = 0


@dataclass
class Scored:
    posting: Posting
    company: str
    cosine: float
    breakdown: dict[str, float | None]
    score: float
    explanation: dict[str, Any]
    also_listed_in: list[str]


@dataclass
class Recommendation:
    request_id: str
    generated_at: datetime
    weights_version: str
    weights: dict[str, float]
    total_candidates: (
        int  # size of the candidate POOL after collapsing (<= POOL_CAP), NOT all matching postings
    )
    results: list[Scored]
    notes: list[str]


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))  # both are L2-normalised


def _conditions(f: Filters, now: datetime) -> list[Any]:
    conds: list[Any] = [Posting.closed_at.is_(None)]
    if not f.include_interns:
        conds.append(Posting.seniority != "intern")
    if f.entry_only:
        conds.append(Posting.is_entry_level.is_(True))
    if f.hide_restricted_sponsorship:
        conds.append(Posting.sponsorship != "restricted")
    if f.role_families:
        conds.append(Posting.role_family.in_(f.role_families))
    if f.companies:
        conds.append(Company.name.in_(f.companies))
    if f.remote_only:
        conds.append(Posting.is_remote.is_(True))
    if f.posted_within_days is not None:
        from datetime import timedelta

        cutoff = now - timedelta(days=f.posted_within_days)
        conds.append(func.coalesce(Posting.source_posted_at, Posting.first_seen_at) >= cutoff)
    if f.location_query and f.location_query.strip():
        q = f"%{f.location_query.strip().lower()}%"
        unknown = (
            (Posting.city.is_(None)) & (Posting.region.is_(None)) & (Posting.country.is_(None))
        )
        # A posting whose location is unknown is NEVER dropped by a location filter (ADR 0011); it is
        # returned and labelled "location not stated" in the explanation.
        conds.append(
            or_(
                func.lower(func.coalesce(Posting.location_raw, "")).like(q),
                func.lower(func.coalesce(Posting.city, "")).like(q),
                func.lower(func.coalesce(Posting.region, "")).like(q),
                func.lower(func.coalesce(Posting.country, "")).like(q),
                unknown,
            )
        )
    return conds


def _retrieve(
    session: Session, query_vec: list[float], f: Filters, now: datetime, k: int
) -> list[tuple[Posting, str, float]]:
    stmt = (
        select(Posting, Company.name, PostingEmbedding.embedding)
        .join(Company, Company.id == Posting.company_id)
        .join(PostingEmbedding, PostingEmbedding.posting_id == Posting.id)
        .where(*_conditions(f, now))
    )
    if session.get_bind().dialect.name == "postgresql":
        # Exact nearest-neighbour search in the database (no ANN index; ADR 0012).
        dist = PostingEmbedding.embedding.op("<=>", return_type=Float)(query_vec)  # cosine distance
        rows = session.execute(
            select(Posting, Company.name, (1 - dist).label("cos"))
            .join(Company, Company.id == Posting.company_id)
            .join(PostingEmbedding, PostingEmbedding.posting_id == Posting.id)
            .where(*_conditions(f, now))
            .order_by(dist)
            .limit(POOL_CAP)  # head-room for repost/variant collapsing
        ).all()
        return [(p, name, float(c)) for p, name, c in rows]
    scored = [(p, name, _cos(query_vec, emb)) for p, name, emb in session.execute(stmt).all()]
    scored.sort(key=lambda t: -t[2])
    return scored[:POOL_CAP]


def _age_days(p: Posting, now: datetime) -> float:
    posted = p.source_posted_at or p.first_seen_at
    return min(max((now - posted).total_seconds() / 86400.0, 0.0), float(RECENCY_CAP_DAYS))


def _location_fit(p: Posting, profile: UserProfile) -> tuple[float, str]:
    unknown = p.city is None and p.region is None and p.country is None
    wanted = [w.lower() for w in profile.target_locations]
    hay = " ".join(x for x in (p.location_raw, p.city, p.region, p.country) if x).lower()
    if wanted and any(w in hay for w in wanted):
        return 1.0, f"matches your target location ({p.location_raw})"
    if p.is_remote and profile.remote_ok:
        return 0.9, "remote, and you are open to remote"
    if unknown and not p.is_remote:
        return NEUTRAL, "location not stated by the company (not penalised)"
    if not wanted:
        return NEUTRAL, "you have no target locations set"
    return 0.1, f"outside your target locations ({p.location_raw or 'unspecified'})"


def recommend(
    session: Session,
    user_id: int,
    f: Filters,
    query_vec: list[float],
    profile: UserProfile,
    now: datetime | None = None,
) -> Recommendation:
    now = now or datetime.now(UTC)
    raw = _retrieve(session, query_vec, f, now, CANDIDATES_K)
    ids = [p.id for p, _, _ in raw]
    skills: dict[int, set[str]] = {i: set() for i in ids}
    if ids:
        for pid, sk in session.execute(
            select(PostingSkill.posting_id, PostingSkill.skill).where(
                PostingSkill.posting_id.in_(ids)
            )
        ):
            skills[pid].add(sk)
    user_skills = {s.lower(): s for s in profile.skills}

    cos_vals = [c for _, _, c in raw]
    lo, hi = (min(cos_vals), max(cos_vals)) if cos_vals else (0.0, 1.0)
    scored: list[Scored] = []
    for p, company, cos in raw:
        post_skills = skills[p.id]
        matched = sorted(s for s in post_skills if s.lower() in user_skills)
        missing = sorted(s for s in post_skills if s.lower() not in user_skills)
        coverage: float | None = (
            (len(matched) / len(post_skills)) if post_skills and user_skills else None
        )
        if p.seniority == "intern":
            sen = INTERN_FIT_WHEN_SHOWN
        else:
            sen = SENIORITY_FIT.get(p.seniority, NEUTRAL)
        loc, loc_text = _location_fit(p, profile)
        age = _age_days(p, now)
        rec = math.exp(-age / RECENCY_TAU_DAYS) if age < RECENCY_CAP_DAYS else 0.0
        cos_norm = (cos - lo) / (hi - lo) if hi > lo else NEUTRAL
        parts = {
            "cosine": cos_norm,
            "skill_coverage": NEUTRAL if coverage is None else coverage,
            "seniority_fit": sen,
            "location_fit": loc,
            "recency": rec,
        }
        total = sum(WEIGHTS[k] * v for k, v in parts.items())
        scored.append(
            Scored(
                posting=p, company=company, cosine=cos,
                breakdown={"cosine": cos, "cosine_normalized": cos_norm, "skill_coverage": coverage, **{k: parts[k] for k in ("seniority_fit", "location_fit", "recency")}},
                score=total,
                explanation=_explain(p, matched, missing, coverage, loc_text, age, profile),
                also_listed_in=[],
            )
        )  # fmt: skip
    scored.sort(key=lambda s: -s.score)
    collapsed, notes = _collapse(scored, f.collapse_variants)
    page = collapsed[f.offset : f.offset + f.limit]
    return Recommendation(
        request_id=str(uuid.uuid4()), generated_at=now, weights_version=WEIGHTS_VERSION, weights=dict(WEIGHTS),
        total_candidates=len(collapsed), results=page, notes=notes,
    )  # fmt: skip


def _collapse(scored: list[Scored], collapse_variants: bool) -> tuple[list[Scored], list[str]]:
    """One result per repost group (canonical_id); optionally one per (company, title) across locations."""
    seen_group: set[int] = set()
    seen_variant: dict[tuple[int, str], Scored] = {}
    out: list[Scored] = []
    dropped_reposts = dropped_variants = 0
    for s in scored:  # already best-score first
        p = s.posting
        group = p.canonical_id or p.id
        if group in seen_group:
            dropped_reposts += 1
            continue
        seen_group.add(group)
        if collapse_variants:
            key = (p.company_id, " ".join(p.title.lower().split()))
            if key in seen_variant:
                loc = p.location_raw or "location not stated"
                if loc not in seen_variant[key].also_listed_in:
                    seen_variant[key].also_listed_in.append(loc)
                dropped_variants += 1
                continue
            seen_variant[key] = s
        out.append(s)
    notes = []
    if dropped_reposts:
        notes.append(f"{dropped_reposts} repost(s) of the same posting were collapsed")
    if dropped_variants:
        notes.append(
            f"{dropped_variants} same-title listings in other locations were collapsed into 'also listed in'"
        )
    return out, notes


def _explain(
    p: Posting,
    matched: list[str],
    missing: list[str],
    coverage: float | None,
    loc_text: str,
    age_days: float,
    profile: UserProfile,
) -> dict[str, Any]:
    if p.is_entry_level:
        level = f'flagged entry-level ({p.entry_evidence}: "{p.entry_evidence_text}")'
    else:
        level = {
            "senior": "senior-level title",
            "mid": "mid-level",
            "intern": "internship",
            "unknown": "level not clear from the posting",
        }.get(p.seniority, p.seniority)
    posted = None
    if p.source_posted_at:
        days = (
            int(age_days)
            if age_days < RECENCY_CAP_DAYS
            else (datetime.now(UTC) - p.source_posted_at).days
        )
        posted = f"company-reported date {p.source_posted_at:%Y-%m-%d} ({days} days ago)" + (
            " - possibly an evergreen listing" if days > 365 else ""
        )
    warning = None
    if p.sponsorship == "restricted" or p.sponsorship_evidence:
        warning = {
            "level": p.sponsorship,
            "snippet": p.sponsorship_evidence,
            "relevant_to_you": bool(profile.needs_sponsorship),
        }
    return {
        "matched_skills": matched[:8],
        "missing_skills": missing[:5],
        "skill_coverage": coverage,
        "seniority": level,
        "location": loc_text,
        "recency": posted or "no company-reported date",
        "sponsorship_warning": warning,
    }
