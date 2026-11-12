"""The pgvector SQL path (PostgreSQL) and the exact Python fallback (SQLite) must rank identically."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from shortlist_ml.db.models import Company, Posting, PostingEmbedding
from shortlist_ml.embeddings.build import embed_open_postings
from shortlist_ml.embeddings.encoder import HashingEncoder
from shortlist_ml.ingest.normalize import build_posting
from shortlist_ml.ingest.store import apply_snapshot
from shortlist_ml.recommend.engine import Filters, _cos, _retrieve
from shortlist_ml.skills.build import enrich_postings


def test_sql_and_python_retrieval_agree_with_a_hand_computed_ranking(session: Session) -> None:
    now = datetime.now(UTC)
    c = Company(name="Acme", ats="greenhouse", board_token="acme", active=True)
    session.add(c)
    session.flush()
    topics = [
        "pytorch machine learning models",
        "sql airflow data pipelines",
        "kubernetes terraform aws infra",
        "react typescript frontend ui",
        "sales quota enterprise accounts",
        "go rust systems backend",
    ]
    apply_snapshot(
        session, c,
        [build_posting(source="greenhouse", external_id=str(i), url="https://x.test", apply_url="https://x.test",
                       title=f"Engineer {i}", description_text=f"Requirements: {t}. " + "word " * 80, location_raw="Austin, TX")
         for i, t in enumerate(topics)],
        now,
    )  # fmt: skip
    enrich_postings(session)
    enc = HashingEncoder()
    embed_open_postings(session, enc)

    q = enc.encode_queries(["machine learning pytorch pipelines"])[0]
    got = _retrieve(session, q, Filters(), now, k=10)
    got_order = [p.id for p, _name, _c in got]
    got_cos = {p.id: c for p, _name, c in got}

    emb = dict(
        session.execute(select(PostingEmbedding.posting_id, PostingEmbedding.embedding)).all()
    )
    want = sorted(emb, key=lambda pid: -_cos(q, emb[pid]))
    assert got_order == want
    for pid, cos in got_cos.items():
        assert abs(cos - _cos(q, emb[pid])) < 1e-4  # same similarity value either way
    top = session.get(Posting, got_order[0])
    assert top is not None and "pytorch" in top.description_text
