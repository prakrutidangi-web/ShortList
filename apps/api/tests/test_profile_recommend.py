import logging
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from shortlist_api import deps
from shortlist_api.main import app
from shortlist_ml.db.models import (
    Company,
    Posting,
    PostingEmbedding,
    ProfileEmbedding,
    User,
    UserProfile,
)
from shortlist_ml.embeddings.build import embed_open_postings
from shortlist_ml.embeddings.encoder import HashingEncoder
from shortlist_ml.ingest.normalize import NormalizedPosting, build_posting
from shortlist_ml.ingest.store import apply_snapshot
from shortlist_ml.skills.build import enrich_postings

NOW = datetime.now(UTC)
FILLER = " detail" * 60


def post(ext: str, title: str, body: str, loc: str, days_ago: int = 5) -> NormalizedPosting:
    return build_posting(
        source="greenhouse", external_id=ext, url=f"https://x.test/{ext}", apply_url=f"https://x.test/{ext}",
        title=title, description_text=f"About us. {FILLER}\nRequirements: {body}{FILLER}", location_raw=loc,
        source_posted_at=NOW - timedelta(days=days_ago),
    )  # fmt: skip


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    with Session(engine, expire_on_commit=False) as s:
        s.add(User(id=1, created_at=NOW))
        acme = Company(name="Acme", ats="greenhouse", board_token="acme", active=True)
        beta = Company(name="Beta", ats="greenhouse", board_token="beta", active=True)
        s.add_all([acme, beta])
        s.flush()
        apply_snapshot(
            s, acme,
            [
                post("1", "Machine Learning Engineer, New Grad", "Python, PyTorch and machine learning. 0-1 years of experience.", "Austin, TX"),
                post("2", "Senior Sales Executive", "Quota carrying, 8+ years of experience in enterprise sales.", "Austin, TX"),
                post("3", "Data Engineer", "SQL, Airflow and Spark pipelines. 3+ years of experience. Visa sponsorship is not available.", "Remote - US"),
                post("4", "Software Engineer Intern", "Python and Git, summer internship.", "Seattle, WA"),
                post("5", "Backend Software Engineer", "Go, PostgreSQL and Kubernetes. 2+ years of experience.", "Hybrid"),
                post("6", "Software Engineer, Platform", "Python and AWS. 2+ years of experience.", "Denver, CO", days_ago=400),
            ],
            NOW,
        )  # fmt: skip
        apply_snapshot(
            s, beta,
            [
                post("7", "Software Engineer, Platform", "Python and AWS. 2+ years of experience.", "Boston, MA"),
                post("8", "Software Engineer, Platform", "Python and AWS. 2+ years of experience.", "Chicago, IL"),
            ],
            NOW,
        )  # fmt: skip
        enrich_postings(s)
        embed_open_postings(s, HashingEncoder())
        s.commit()

    def override_session() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as sess:
            yield sess
            sess.commit()

    app.dependency_overrides[deps.get_session] = override_session
    app.dependency_overrides[deps.get_cached_encoder] = HashingEncoder
    yield TestClient(app)
    app.dependency_overrides.clear()


PROFILE = {
    "skills": ["Python", "PyTorch", "Machine Learning", "SQL"],
    "target_roles": ["ml_ai", "software_engineering"],
    "target_locations": ["Austin"],
    "remote_ok": True,
    "grad_date": "2027-05-01",
    "needs_sponsorship": False,
    "about_text": "Interested in recommender systems.",
}


def titles(resp) -> list[str]:  # type: ignore[no-untyped-def]
    return [r["title"] for r in resp.json()["results"]]


# ---------------------------------------------------------------- minimal text PDFs (no external deps)
def make_pdf(lines: list[str]) -> bytes:
    def esc(t: str) -> str:
        return (
            t.replace(chr(92), chr(92) * 2).replace("(", chr(92) + "(").replace(")", chr(92) + ")")
        )

    stream = (
        "BT /F1 11 Tf 40 760 Td 14 TL " + " ".join(f"({esc(line)}) Tj T*" for line in lines) + " ET"
    )
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 5 0 R /Resources << /Font << /F1 4 0 R >> >> >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


RESUME_LINES = [
    "Jane Q. Testperson  |  jane.testperson@example.com  |  (555) 010-0199",
    "Education: B.S. Computer Science, Test University. Expected graduation: May 2027.",
    "Skills: Python, SQL, PyTorch, Docker, Git, AWS, React, TypeScript, PostgreSQL, Kafka.",
    "Projects: built a recommender system with embeddings and a machine learning pipeline in Python.",
    "Experience: software engineering intern, wrote unit tests with pytest and used CI/CD with GitHub Actions.",
]


def test_pdf_resume_returns_suggestions_and_stores_nothing(
    client: TestClient, engine: Engine
) -> None:
    r = client.post(
        "/profile/resume", files={"file": ("resume.pdf", make_pdf(RESUME_LINES), "application/pdf")}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "pdf" and {
        "Python",
        "SQL",
        "PyTorch",
        "Docker",
        "AWS",
        "TypeScript",
    } <= set(body["skills"])
    assert body["grad_date"] == "2027-05-01" and "2027" in body["grad_date_evidence"]
    assert (
        "jane" not in r.text.lower() and "example.com" not in r.text and "555" not in r.text
    )  # no PII echoed back
    with Session(engine) as s:  # parsing alone persists nothing
        assert s.scalar(select(func.count()).select_from(UserProfile)) == 0


def test_resume_input_errors_are_clear_and_pii_free(client: TestClient) -> None:
    scanned = make_pdf(["x"])  # a PDF with (almost) no text layer
    cases = [
        (dict(files={"file": ("a.pdf", scanned, "application/pdf")}), "no_text_layer"),
        (dict(files={"file": ("a.pdf", b"not a pdf at all" * 20, "application/pdf")}), "not_pdf"),
        (
            dict(
                files={
                    "file": (
                        "a.pdf",
                        b"%PDF-1.4\n" + b"0" * (5 * 1024 * 1024 + 10),
                        "application/pdf",
                    )
                }
            ),
            "too_large",
        ),
        (dict(files={"file": ("a.pdf", b"%PDF-1.4\ngarbage", "application/pdf")}), "unreadable"),
        (dict(data={"text": "hi"}), "too_short"),
        (dict(data={}), "missing"),
    ]
    for kwargs, code in cases:
        r = client.post("/profile/resume", **kwargs)  # type: ignore[arg-type]
        assert r.status_code == 422 and r.json()["detail"]["code"] == code, (code, r.text)


def test_pasted_text_path(client: TestClient) -> None:
    r = client.post("/profile/resume", data={"text": "\n".join(RESUME_LINES)})
    assert r.status_code == 200 and r.json()["source"] == "text" and "Python" in r.json()["skills"]


def test_profile_crud_and_validation(client: TestClient) -> None:
    assert client.get("/profile").status_code == 404
    r = client.put("/profile", json=PROFILE)
    assert r.status_code == 200
    out = r.json()
    assert out["skills"][:2] == ["Python", "PyTorch"] and out["profile_document"].startswith(
        "New graduate seeking"
    )
    assert (
        "machine learning and AI" in out["profile_document"]
        and "recommender systems" in out["profile_document"]
    )
    assert client.get("/profile").json()["profile_document"] == out["profile_document"]
    prev = client.post("/profile/preview-document", json=PROFILE).json()["profile_document"]
    assert prev == out["profile_document"]  # what the user previews is exactly what gets embedded
    assert (
        client.put("/profile", json={**PROFILE, "target_roles": ["astronaut"]}).status_code == 422
    )
    assert client.put("/profile", json={**PROFILE, "skills": ["x" * 100]}).status_code == 422


def test_recommend_requires_a_profile(client: TestClient) -> None:
    assert client.get("/recommend").status_code == 409


def test_recommend_shape_request_id_breakdown_and_sane_ranking(client: TestClient) -> None:
    client.put("/profile", json=PROFILE)
    r = client.get("/recommend", params={"include_interns": True, "collapse_variants": False})
    assert r.status_code == 200
    body = r.json()
    uuid.UUID(body["request_id"])  # a real UUID
    assert body["weights_version"] == "untuned-v0" and "UNTUNED" in body["disclaimer"]
    assert abs(sum(body["weights"].values()) - 1.0) < 1e-9
    assert [x["position"] for x in body["results"]] == list(range(1, len(body["results"]) + 1))
    first = body["results"][0]
    assert set(first["breakdown"]) == {
        "cosine",
        "cosine_normalized",
        "skill_coverage",
        "seniority_fit",
        "location_fit",
        "recency",
    }
    assert {
        "matched_skills",
        "missing_skills",
        "seniority",
        "location",
        "recency",
        "sponsorship_warning",
    } <= set(first["explanation"])
    assert (
        first["title"] == "Machine Learning Engineer, New Grad"
    )  # PyTorch/ML/Austin/entry-level beats everything
    assert first["is_entry_level"] and first["entry_evidence"]["rule"] == "title_keyword"
    assert set(first["explanation"]["matched_skills"]) >= {"Python", "PyTorch"}
    scores = [x["score"] for x in body["results"]]
    assert scores == sorted(scores, reverse=True)  # best score first
    order = [x["title"] for x in body["results"]]
    assert order.index("Machine Learning Engineer, New Grad") < order.index(
        "Senior Sales Executive"
    )
    sales = next(x for x in body["results"] if x["title"] == "Senior Sales Executive")
    assert sales["breakdown"]["seniority_fit"] < first["breakdown"]["seniority_fit"]
    assert sales["breakdown"]["skill_coverage"] in (
        0.0,
        None,
    )  # none of the profile's skills are in a sales posting
    assert (
        client.get("/recommend").json()["request_id"] != body["request_id"]
    )  # fresh id per request


def test_filters(client: TestClient) -> None:
    client.put("/profile", json=PROFILE)
    allr = titles(client.get("/recommend", params={"collapse_variants": False}))
    assert "Software Engineer Intern" not in allr  # interns hidden by default
    assert "Software Engineer Intern" in titles(
        client.get("/recommend", params={"include_interns": True, "collapse_variants": False})
    )
    assert titles(client.get("/recommend", params={"entry_only": True})) == [
        "Machine Learning Engineer, New Grad"
    ]
    assert set(titles(client.get("/recommend", params={"role_family": "data_engineering"}))) == {
        "Data Engineer"
    }
    assert set(
        titles(client.get("/recommend", params={"company": "Beta", "collapse_variants": False}))
    ) == {"Software Engineer, Platform"}
    assert titles(client.get("/recommend", params={"remote_only": True})) == ["Data Engineer"]

    # hiding 'restricted' sponsorship removes ONLY the explicit "visa sponsorship is not available" posting
    hidden = titles(
        client.get(
            "/recommend", params={"hide_restricted_sponsorship": True, "collapse_variants": False}
        )
    )
    assert "Data Engineer" not in hidden and set(allr) - set(hidden) == {"Data Engineer"}

    recent = client.get(
        "/recommend", params={"posted_within_days": 30, "collapse_variants": False}
    ).json()["results"]
    assert (
        all(x["posted_at"] for x in recent) and len(recent) == len(allr) - 1
    )  # the 400-day-old posting is gone

    # explicit location filter: matches Austin AND keeps postings whose location is unknown ("Hybrid"); never drops them
    loc = titles(
        client.get("/recommend", params={"location": "austin", "collapse_variants": False})
    )
    assert (
        "Machine Learning Engineer, New Grad" in loc and "Backend Software Engineer" in loc
    )  # unknown-location kept
    assert "Data Engineer" not in loc  # a known, different location is excluded


def test_unknown_location_is_neutral_not_penalised(client: TestClient) -> None:
    client.put("/profile", json=PROFILE)
    res = client.get("/recommend", params={"collapse_variants": False}).json()["results"]
    backend = next(r for r in res if r["title"] == "Backend Software Engineer")
    assert (
        backend["breakdown"]["location_fit"] == 0.5
        and "not stated" in backend["explanation"]["location"]
    )
    far = next(
        r
        for r in res
        if r["title"] == "Software Engineer, Platform" and r["location_raw"] == "Boston, MA"
    )
    assert far["breakdown"]["location_fit"] == 0.1


def test_sponsorship_is_a_warning_and_nothing_else(client: TestClient) -> None:
    client.put("/profile", json={**PROFILE, "needs_sponsorship": True})
    res = client.get("/recommend", params={"collapse_variants": False}).json()["results"]
    de = next(r for r in res if r["title"] == "Data Engineer")
    w = de["explanation"]["sponsorship_warning"]
    assert (
        w["level"] == "restricted"
        and "sponsorship is not available" in w["snippet"]
        and w["relevant_to_you"] is True
    )


def test_same_title_listings_collapse_into_also_listed_in(client: TestClient) -> None:
    client.put("/profile", json=PROFILE)
    collapsed = client.get("/recommend").json()
    plat = [r for r in collapsed["results"] if r["title"] == "Software Engineer, Platform"]
    assert len(plat) == 2  # one per company (Acme's and Beta's), not 3
    beta = next(r for r in plat if r["also_listed_in"])
    assert set(beta["also_listed_in"]) == {"Boston, MA", "Chicago, IL"} - {beta["location_raw"]}
    assert any("collapsed" in n for n in collapsed["notes"])
    assert (
        len(
            [
                r
                for r in client.get("/recommend", params={"collapse_variants": False}).json()[
                    "results"
                ]
                if r["title"] == "Software Engineer, Platform"
            ]
        )
        == 3
    )


def test_pagination(client: TestClient) -> None:
    client.put("/profile", json=PROFILE)
    full = titles(client.get("/recommend", params={"collapse_variants": False, "limit": 100}))
    page = client.get(
        "/recommend", params={"collapse_variants": False, "limit": 2, "offset": 2}
    ).json()
    assert [r["title"] for r in page["results"]] == full[2:4] and [
        r["position"] for r in page["results"]
    ] == [3, 4]


def test_meta(client: TestClient) -> None:
    m = client.get("/meta").json()
    assert m["total_open"] == 8 and {c["name"]: c["open"] for c in m["companies"]} == {
        "Acme": 6,
        "Beta": 2,
    }
    assert "ml_ai" in m["role_families"]


# ---------------------------------------------------------------- delete-my-data (profile, derived data, embedding)
def test_delete_profile_removes_profile_derived_data_and_embedding(
    client: TestClient, engine: Engine
) -> None:
    client.post(
        "/profile/resume", files={"file": ("r.pdf", make_pdf(RESUME_LINES), "application/pdf")}
    )
    client.put("/profile", json=PROFILE)
    with Session(engine) as s:
        assert s.get(UserProfile, 1) is not None and s.get(ProfileEmbedding, 1) is not None
        postings_before = s.scalar(select(func.count()).select_from(Posting))
        embeds_before = s.scalar(select(func.count()).select_from(PostingEmbedding))

    r = client.delete("/profile")
    assert r.status_code == 200 and r.json() == {"deleted": {"profile": True, "embedding": True}}
    with Session(engine) as s:
        assert (
            s.get(UserProfile, 1) is None
        )  # profile + every derived field (skills, roles, locations, grad date, about, document)
        assert s.get(ProfileEmbedding, 1) is None  # the embedding
        assert s.scalar(select(func.count()).select_from(UserProfile)) == 0
        assert s.scalar(select(func.count()).select_from(ProfileEmbedding)) == 0
        # public job data is untouched
        assert s.scalar(select(func.count()).select_from(Posting)) == postings_before
        assert s.scalar(select(func.count()).select_from(PostingEmbedding)) == embeds_before
    assert client.get("/profile").status_code == 404
    assert client.get("/recommend").status_code == 409  # recommendations stop immediately
    assert client.delete("/profile").json() == {
        "deleted": {"profile": False, "embedding": False}
    }  # idempotent


# ---------------------------------------------------------------- privacy: no PII in logs or storage
def test_no_resume_pii_in_logs_or_database(
    client: TestClient, engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    secrets = [
        "jane.testperson@example.com",
        "(555) 010-0199",
        "555-010-0199",
        "Jane Q. Testperson",
        "Testperson",
    ]
    caplog.set_level(logging.DEBUG)
    pdf = make_pdf(RESUME_LINES)
    client.post(
        "/profile/resume", files={"file": ("Jane_Testperson_Resume.pdf", pdf, "application/pdf")}
    )
    client.post("/profile/resume", data={"text": "\n".join(RESUME_LINES)})
    client.post("/profile/resume", files={"file": ("bad.pdf", b"nope", "application/pdf")})
    client.put("/profile", json=PROFILE)
    client.get("/recommend")
    logged = caplog.text + " ".join(r.getMessage() for r in caplog.records)
    for secret in secrets:
        assert secret not in logged, f"PII leaked into logs: {secret}"
    assert "Jane_Testperson_Resume" not in logged  # file names are not logged either
    with Session(engine) as s:
        row = s.get(UserProfile, 1)
        assert row is not None
        stored = " ".join(
            [row.profile_document, str(row.skills), str(row.target_locations), row.about_text or ""]
        )
        for secret in secrets:
            assert secret not in stored


def test_redaction_filter_scrubs_emails_and_phones() -> None:
    from shortlist_api.privacy import redact

    assert redact("mail me@x.org or call (555) 010-0199") == "mail [email] or call [phone]"
    assert re.search(r"\d{3}-\d{3}-\d{4}", redact("555-010-0199")) is None


def test_missing_ml_dependencies_is_a_clear_503(client: TestClient) -> None:
    from shortlist_ml.embeddings.encoder import MissingMLDependencies

    def broken() -> object:
        raise MissingMLDependencies("Install the ML dependencies first: make install-ml")

    app.dependency_overrides[deps.get_cached_encoder] = broken
    r = client.put("/profile", json=PROFILE)
    assert r.status_code == 503 and "make install-ml" in r.json()["detail"]
