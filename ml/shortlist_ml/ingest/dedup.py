import hashlib
import re

from shortlist_ml.ingest.normalize import NormalizedPosting


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def dedup_key(company_id: int, p: NormalizedPosting) -> str:
    """Identity of a job's *content within a company*: same title, location and description text
    => same job, even if the ATS issued a new posting id (a repost).

    Exact match on normalized text only. Deliberately NOT fuzzy: we have no evidence yet of how
    many near-duplicates exist, and a fuzzy rule could wrongly merge distinct roles.
    """
    desc = hashlib.sha256(_norm(p.description_text).encode()).hexdigest()
    payload = "\x1f".join([str(company_id), _norm(p.title), _norm(p.location_raw), desc])
    return hashlib.sha256(payload.encode()).hexdigest()
