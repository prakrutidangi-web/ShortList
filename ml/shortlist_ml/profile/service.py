"""Save / load / delete the profile and its embedding."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from shortlist_ml.db.models import ProfileEmbedding, UserProfile
from shortlist_ml.embeddings.encoder import Encoder
from shortlist_ml.profile.build import TARGETABLE_ROLES, profile_document

MAX_SKILLS = 80
MAX_LOCATIONS = 12


class ProfileValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ProfileInput:
    skills: list[str]
    target_roles: list[str]
    target_locations: list[str]
    remote_ok: bool
    grad_date: date | None
    needs_sponsorship: bool
    about_text: str | None


def _clean_list(items: list[str], limit: int, maxlen: int, what: str) -> list[str]:
    out: list[str] = []
    for raw in items:
        s = " ".join(raw.split())
        if s and s.lower() not in {x.lower() for x in out}:
            if len(s) > maxlen:
                raise ProfileValidationError(f"{what} entry too long")
            out.append(s)
    if len(out) > limit:
        raise ProfileValidationError(f"too many {what} (max {limit})")
    return out


def validate(data: ProfileInput) -> ProfileInput:
    roles = _clean_list(data.target_roles, 8, 40, "roles")
    bad = [r for r in roles if r not in TARGETABLE_ROLES]
    if bad:
        raise ProfileValidationError(f"unknown role family: {bad[0]}")
    about = data.about_text.strip() if data.about_text else None
    if about and len(about) > 1500:
        raise ProfileValidationError("about text too long (max 1500 characters)")
    return ProfileInput(
        skills=_clean_list(data.skills, MAX_SKILLS, 60, "skills"),
        target_roles=roles,
        target_locations=_clean_list(data.target_locations, MAX_LOCATIONS, 80, "locations"),
        remote_ok=data.remote_ok,
        grad_date=data.grad_date,
        needs_sponsorship=data.needs_sponsorship,
        about_text=about or None,
    )


def save_profile(
    session: Session, user_id: int, data: ProfileInput, encoder: Encoder
) -> UserProfile:
    data = validate(data)
    doc = profile_document(data.skills, data.target_roles, data.about_text, data.grad_date)
    vec = encoder.encode_queries([doc])[0]
    now = datetime.now(UTC)
    row = session.merge(
        UserProfile(
            user_id=user_id, skills=data.skills, target_roles=data.target_roles,
            target_locations=data.target_locations, remote_ok=data.remote_ok, grad_date=data.grad_date,
            needs_sponsorship=data.needs_sponsorship, about_text=data.about_text,
            profile_document=doc, updated_at=now,
        )
    )  # fmt: skip
    session.merge(
        ProfileEmbedding(
            user_id=user_id, model=encoder.name,
            text_hash=hashlib.sha256(f"{encoder.name}\x1f{doc}".encode()).hexdigest(),
            embedding=vec, updated_at=now,
        )
    )  # fmt: skip
    session.flush()
    return row


def get_profile(session: Session, user_id: int) -> UserProfile | None:
    return session.get(UserProfile, user_id)


def get_profile_embedding(session: Session, user_id: int) -> ProfileEmbedding | None:
    return session.get(ProfileEmbedding, user_id)


def delete_profile(session: Session, user_id: int) -> dict[str, bool]:
    """Delete the profile, every field derived from the resume, and the profile embedding.

    Raw resumes are never stored, so there is nothing else to remove. Interaction logs (Phase 3) will be
    added here when they exist."""
    had_emb = (
        session.scalars(select(ProfileEmbedding).where(ProfileEmbedding.user_id == user_id)).first()
        is not None
    )
    had_prof = (
        session.scalars(select(UserProfile).where(UserProfile.user_id == user_id)).first()
        is not None
    )
    session.execute(delete(ProfileEmbedding).where(ProfileEmbedding.user_id == user_id))
    session.execute(delete(UserProfile).where(UserProfile.user_id == user_id))
    session.flush()
    return {"profile": had_prof, "embedding": had_emb}
