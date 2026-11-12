from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class ProfileIn(BaseModel):
    skills: list[str] = Field(default_factory=list, max_length=200)
    target_roles: list[str] = Field(default_factory=list, max_length=8)
    target_locations: list[str] = Field(default_factory=list, max_length=20)
    remote_ok: bool = True
    grad_date: date | None = None
    needs_sponsorship: bool = False
    about_text: str | None = Field(default=None, max_length=1500)


class ProfileOut(ProfileIn):
    profile_document: str
    updated_at: datetime


class SuggestionOut(BaseModel):
    source: str  # "pdf" | "text"
    characters_read: int
    skills: list[str]
    grad_date: date | None
    grad_date_evidence: str | None
    note: str = "Nothing has been saved. Review and edit these suggestions, then save your profile."


class DocumentPreview(BaseModel):
    profile_document: str


class DeleteOut(BaseModel):
    deleted: dict[str, bool]


class EntryEvidence(BaseModel):
    rule: str | None
    text: str | None


class ResultOut(BaseModel):
    position: int  # 1-based rank in this response (Phase 3 impression logging attaches here)
    posting_id: int
    company: str
    title: str
    location_raw: str | None
    city: str | None
    region: str | None
    country: str | None
    is_remote: bool | None
    role_family: str | None
    seniority: str
    is_entry_level: bool
    entry_evidence: EntryEvidence
    apply_url: str
    posted_at: datetime | None
    score: float
    breakdown: dict[str, float | None]
    explanation: dict[str, Any]
    also_listed_in: list[str]


class RecommendOut(BaseModel):
    request_id: str
    generated_at: datetime
    weights_version: str
    weights: dict[str, float]
    disclaimer: str
    total_candidates: (
        int  # size of the retrieved candidate pool (top POOL_CAP by similarity) after collapsing
    )
    candidate_pool_cap: int
    notes: list[str]
    timing_ms: float
    results: list[ResultOut]


class MetaOut(BaseModel):
    total_open: int
    role_families: list[str]
    companies: list[dict[str, Any]]
