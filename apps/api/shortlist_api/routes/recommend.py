import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shortlist_api.deps import get_session, get_user_id
from shortlist_api.schemas import EntryEvidence, MetaOut, RecommendOut, ResultOut
from shortlist_ml.db.models import Company, Posting
from shortlist_ml.profile import service
from shortlist_ml.recommend.engine import POOL_CAP, Filters, recommend
from shortlist_ml.skills.extract import ROLE_FAMILIES

router = APIRouter(tags=["recommend"])

DISCLAIMER = (
    "Scores come from a hand-weighted content-based scorer with UNTUNED weights. They have not been measured "
    "against any baseline yet and should not be read as evidence that this ranking is good."
)


@router.get("/recommend", response_model=RecommendOut)
def get_recommendations(
    session: Annotated[Session, Depends(get_session)],
    user_id: Annotated[int, Depends(get_user_id)],
    location: str | None = None,
    remote_only: bool = False,
    role_family: Annotated[list[str] | None, Query()] = None,
    company: Annotated[list[str] | None, Query()] = None,
    posted_within_days: Annotated[int | None, Query(ge=1, le=3650)] = None,
    include_interns: bool = False,
    entry_only: bool = False,
    hide_restricted_sponsorship: bool = False,
    collapse_variants: bool = True,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RecommendOut:
    t0 = time.perf_counter()
    profile = service.get_profile(session, user_id)
    emb = service.get_profile_embedding(session, user_id)
    if profile is None or emb is None:
        raise HTTPException(
            409, "Create your profile first (upload a resume or enter your skills)."
        )
    bad = [r for r in (role_family or []) if r not in ROLE_FAMILIES]
    if bad:
        raise HTTPException(422, f"unknown role_family: {bad[0]}")
    filters = Filters(
        location_query=location, remote_only=remote_only, role_families=role_family or [], companies=company or [],
        posted_within_days=posted_within_days, include_interns=include_interns, entry_only=entry_only,
        hide_restricted_sponsorship=hide_restricted_sponsorship, collapse_variants=collapse_variants,
        limit=limit, offset=offset,
    )  # fmt: skip
    rec = recommend(session, user_id, filters, emb.embedding, profile)
    results = [
        ResultOut(
            position=offset + i + 1, posting_id=s.posting.id, company=s.company, title=s.posting.title,
            location_raw=s.posting.location_raw, city=s.posting.city, region=s.posting.region, country=s.posting.country,
            is_remote=s.posting.is_remote, role_family=s.posting.role_family, seniority=s.posting.seniority,
            is_entry_level=s.posting.is_entry_level,
            entry_evidence=EntryEvidence(rule=s.posting.entry_evidence, text=s.posting.entry_evidence_text),
            apply_url=s.posting.apply_url, posted_at=s.posting.source_posted_at, score=round(s.score, 4),
            breakdown={k: (None if v is None else round(v, 4)) for k, v in s.breakdown.items()},
            explanation=s.explanation, also_listed_in=s.also_listed_in[:6],
        )
        for i, s in enumerate(rec.results)
    ]  # fmt: skip
    return RecommendOut(
        request_id=rec.request_id, generated_at=rec.generated_at, weights_version=rec.weights_version, weights=rec.weights,
        disclaimer=DISCLAIMER, total_candidates=rec.total_candidates, candidate_pool_cap=POOL_CAP, notes=rec.notes,
        timing_ms=round((time.perf_counter() - t0) * 1000, 1), results=results,
    )  # fmt: skip


@router.get("/meta", response_model=MetaOut)
def meta(session: Annotated[Session, Depends(get_session)]) -> MetaOut:
    rows = session.execute(
        select(Company.name, func.count(Posting.id))
        .join(Posting, Posting.company_id == Company.id)
        .where(Posting.closed_at.is_(None))
        .group_by(Company.name)
        .order_by(Company.name)
    ).all()
    return MetaOut(
        total_open=sum(int(n) for _, n in rows),
        role_families=list(ROLE_FAMILIES),
        companies=[{"name": name, "open": int(n)} for name, n in rows],
    )
