"""Fill postings.role_family and posting_skills for every posting (idempotent, recomputed each run)."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from shortlist_ml.db.models import Company, Posting, PostingSkill
from shortlist_ml.skills.extract import classify_role_family, skills_for_posting


def enrich_postings(session: Session) -> tuple[int, int]:
    """Returns (postings whose role_family changed, postings whose skill set changed)."""
    have: dict[int, set[str]] = {}
    for pid, skill in session.execute(select(PostingSkill.posting_id, PostingSkill.skill)):
        have.setdefault(pid, set()).add(skill)
    fam_changed = skills_changed = 0
    names = dict(session.execute(select(Company.id, Company.name)).all())
    for p in session.scalars(select(Posting)):
        family = classify_role_family(p.title)
        if p.role_family != family:
            p.role_family = family
            fam_changed += 1
        want = set(skills_for_posting(p.title, p.description_text, names.get(p.company_id, "")))
        cur = have.get(p.id, set())
        if want != cur:
            session.execute(delete(PostingSkill).where(PostingSkill.posting_id == p.id))
            session.add_all([PostingSkill(posting_id=p.id, skill=s) for s in sorted(want)])
            skills_changed += 1
    session.flush()
    return fam_changed, skills_changed
