"""Embed OPEN postings, incrementally: a posting is (re-)embedded only when it has no embedding, its
document text changed, or the model changed (all folded into text_hash). Closed postings are skipped."""

import hashlib
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from shortlist_ml.db.models import Posting, PostingEmbedding, PostingSkill
from shortlist_ml.embeddings.documents import posting_document
from shortlist_ml.embeddings.encoder import Encoder


@dataclass
class EmbedStats:
    open_postings: int = 0
    embedded: int = 0
    unchanged: int = 0
    seconds: float = 0.0


def text_hash(model_name: str, document: str) -> str:
    return hashlib.sha256(f"{model_name}\x1f{document}".encode()).hexdigest()


def embed_open_postings(
    session: Session,
    encoder: Encoder,
    *,
    batch_size: int = 64,
    limit: int | None = None,
    on_batch: Callable[[int, int], None] | None = None,
) -> EmbedStats:
    stats = EmbedStats()
    skills: dict[int, list[str]] = defaultdict(list)
    for pid, skill in session.execute(
        select(PostingSkill.posting_id, PostingSkill.skill).order_by(PostingSkill.skill)
    ):
        skills[pid].append(skill)
    existing: dict[int, str] = dict(
        session.execute(select(PostingEmbedding.posting_id, PostingEmbedding.text_hash)).all()
    )

    todo: list[tuple[int, str, str]] = []
    for p in session.scalars(
        select(Posting).where(Posting.closed_at.is_(None)).order_by(Posting.id)
    ):
        stats.open_postings += 1
        doc = posting_document(
            p.title, p.role_family, p.seniority, skills.get(p.id, []), p.description_text
        )
        h = text_hash(encoder.name, doc)
        if existing.get(p.id) == h:
            stats.unchanged += 1
        else:
            todo.append((p.id, doc, h))
    if limit is not None:
        todo = todo[:limit]

    start = time.perf_counter()
    for i in range(0, len(todo), batch_size):
        chunk = todo[i : i + batch_size]
        vectors = encoder.encode_documents([d for _, d, _ in chunk])
        now = datetime.now(UTC)
        for (pid, _doc, h), vec in zip(chunk, vectors, strict=True):
            session.merge(
                PostingEmbedding(
                    posting_id=pid, model=encoder.name, text_hash=h, embedding=vec, updated_at=now
                )
            )
        session.commit()
        stats.embedded += len(chunk)
        if on_batch:
            on_batch(stats.embedded, len(todo))
    stats.seconds = time.perf_counter() - start
    return stats
