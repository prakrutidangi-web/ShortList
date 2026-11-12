import math
from datetime import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shortlist_ml.db.models import Company, Posting, PostingEmbedding
from shortlist_ml.embeddings.build import embed_open_postings
from shortlist_ml.embeddings.documents import posting_document
from shortlist_ml.embeddings.encoder import QUERY_PREFIX, HashingEncoder
from shortlist_ml.ingest.normalize import NormalizedPosting, build_posting
from shortlist_ml.ingest.store import apply_snapshot


def cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_hashing_encoder_properties() -> None:
    enc = HashingEncoder()
    a, a2, near, far = enc.encode_documents(
        [
            "python machine learning engineer",
            "python machine learning engineer",
            "machine learning python role",
            "sales account executive quota",
        ]
    )
    assert len(a) == enc.dim == 384
    assert math.isclose(math.sqrt(sum(x * x for x in a)), 1.0, rel_tol=1e-9)
    assert a == a2  # deterministic
    assert cos(a, near) > cos(a, far)  # shared words -> more similar (lexical only, not semantic)
    assert enc.encode_queries(["x y"]) == enc.encode_documents(["x y"])


def test_query_prefix_is_the_documented_bge_instruction() -> None:
    assert QUERY_PREFIX == "Represent this sentence for searching relevant passages: "


def test_posting_document_uses_role_section_skills_and_caps_length() -> None:
    desc = "Company intro text. " * 40 + "Requirements: Python. " + "detail " * 600
    doc = posting_document("Data Engineer", "data_engineering", "entry", ["Python", "SQL"], desc)
    assert doc.startswith(
        "Data Engineer\nRole: data_engineering; level: entry\nSkills: Python, SQL\nRequirements"
    )
    assert len(doc) < 1700 and "Company intro" not in doc


@pytest.fixture
def two_open_one_closed(session: Session, t0: datetime) -> Session:
    c = Company(name="Acme", ats="greenhouse", board_token="acme", active=True)
    session.add(c)
    session.flush()

    def p(i: str, title: str, desc: str) -> NormalizedPosting:
        return build_posting(
            source="greenhouse", external_id=i, url="https://x.test", apply_url=f"https://x.test/{i}",
            title=title, description_text=desc, location_raw="Austin, TX",
        )  # fmt: skip

    apply_snapshot(
        session,
        c,
        [
            p("1", "ML Engineer", "Requirements: PyTorch. " + "a " * 200),
            p("2", "Data Engineer", "Requirements: SQL. " + "b " * 200),
            p("3", "Sales", "Quota. " * 60),
        ],
        t0,
    )
    # close #3: 2 of 3 still open is not a >50% drop
    apply_snapshot(
        session,
        c,
        [
            p("1", "ML Engineer", "Requirements: PyTorch. " + "a " * 200),
            p("2", "Data Engineer", "Requirements: SQL. " + "b " * 200),
        ],
        t0.replace(day=t0.day + 1),
    )
    return session


def test_embeds_only_open_postings_and_is_incremental(two_open_one_closed: Session) -> None:
    s = two_open_one_closed
    enc = HashingEncoder()
    st = embed_open_postings(s, enc, batch_size=1)
    assert (st.open_postings, st.embedded, st.unchanged) == (
        2,
        2,
        0,
    )  # the closed posting is skipped
    assert s.scalar(select(func.count()).select_from(PostingEmbedding)) == 2

    st2 = embed_open_postings(s, enc)
    assert (st2.embedded, st2.unchanged) == (0, 2)  # nothing to do the second time

    p1 = s.scalars(select(Posting).where(Posting.external_id == "1")).one()
    p1.description_text = "Requirements: JAX and Rust. " + "c " * 200  # text changed (hash-based)
    s.flush()
    st3 = embed_open_postings(s, enc)
    assert (st3.embedded, st3.unchanged) == (1, 1)

    class OtherModel(HashingEncoder):
        name = "another-model"

    st4 = embed_open_postings(s, OtherModel())  # model change re-embeds everything
    assert st4.embedded == 2
    assert {m for (m,) in s.execute(select(PostingEmbedding.model))} == {"another-model"}


def test_limit_caps_work(two_open_one_closed: Session) -> None:
    assert embed_open_postings(two_open_one_closed, HashingEncoder(), limit=1).embedded == 1
