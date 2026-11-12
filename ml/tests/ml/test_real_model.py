"""Tests with the REAL bge-small-en-v1.5 model. Skipped unless RUN_MODEL_TESTS=1 and the ml group is installed
(`make install-ml`, then `make test-model`). They are never run in CI."""

import math
import os

import pytest

pytestmark = pytest.mark.model

if not os.environ.get("RUN_MODEL_TESTS"):
    pytest.skip("set RUN_MODEL_TESTS=1 (make test-model)", allow_module_level=True)
pytest.importorskip("sentence_transformers")

from shortlist_ml.embeddings.encoder import MODEL_NAME, SentenceTransformerEncoder  # noqa: E402


@pytest.fixture(scope="module")
def enc() -> SentenceTransformerEncoder:
    return SentenceTransformerEncoder()


def cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_shape_normalisation_and_device(enc: SentenceTransformerEncoder) -> None:
    assert enc.name == MODEL_NAME and enc.dim == 384
    assert enc.device in ("mps", "cuda", "cpu")
    v = enc.encode_documents(["Machine learning engineer working on ranking models in PyTorch"])[0]
    assert len(v) == 384 and math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, rel_tol=1e-3)


def test_semantic_ranking_beats_unrelated_text(enc: SentenceTransformerEncoder) -> None:
    docs = [
        "Machine Learning Engineer. Train and ship ranking and recommendation models in Python and PyTorch.",
        "Data Engineer. Build ETL pipelines with Spark, Airflow and SQL on a cloud data warehouse.",
        "Enterprise Account Executive. Own a quota, close large software deals and manage customer relationships.",
        "Recruiting Coordinator. Schedule interviews and support the hiring team.",
    ]
    d = enc.encode_documents(docs)
    q_ml = enc.encode_queries(
        [
            "New graduate seeking machine learning roles. Skills: Python, PyTorch, recommender systems."
        ]
    )[0]
    q_de = enc.encode_queries(
        ["New graduate seeking data engineering roles. Skills: SQL, Spark, Airflow, ETL."]
    )[0]
    ml_scores = [cos(q_ml, x) for x in d]
    de_scores = [cos(q_de, x) for x in d]
    assert max(range(4), key=ml_scores.__getitem__) == 0
    assert max(range(4), key=de_scores.__getitem__) == 1
    assert ml_scores[0] > ml_scores[2] and ml_scores[0] > ml_scores[3]
    assert de_scores[1] > de_scores[2] and de_scores[1] > de_scores[3]


def test_query_instruction_changes_the_query_embedding(enc: SentenceTransformerEncoder) -> None:
    text = "python machine learning"
    assert enc.encode_queries([text])[0] != enc.encode_documents([text])[0]
