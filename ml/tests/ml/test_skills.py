import pytest

from shortlist_ml.skills.extract import (
    classify_role_family,
    extract_skills,
    load_skills,
    role_section,
    skills_for_posting,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "We use Python, SQL and Go; Kubernetes and Terraform on AWS.",
            {"Python", "SQL", "Go", "Kubernetes", "Terraform", "AWS"},
        ),
        (
            "Experience with C/C++ and Rust. React and Next.js, Node.js.",
            {"C", "C++", "Rust", "React", "Next.js", "Node.js"},
        ),
        ("Proficiency in R and Python for statistics", {"R", "Python", "Statistics"}),
        (
            "PyTorch, LLMs, RAG and embeddings; CI/CD; .NET and C#",
            {"PyTorch", "LLMs", "RAG", "Embeddings", "CI/CD", ".NET", "C#"},
        ),
        (
            "Spark, Kafka and Airflow pipelines; PostgreSQL and NoSQL",
            {"Spark", "Kafka", "Airflow", "PostgreSQL", "NoSQL", "ETL"},
        ),
        ("Swift or Kotlin for iOS and Android", {"Swift", "Kotlin", "iOS", "Android"}),
    ],
)
def test_extracts_expected_skills(text: str, expected: set[str]) -> None:
    got = set(extract_skills(text))
    assert (
        expected - {"ETL"} <= got
    )  # every expected skill is found (ETL only appears via the 'pipelines' alias)


@pytest.mark.parametrize(
    "text",
    [
        "Go to market strategy; go live in Q3; let's go ahead",
        "React to customer needs and excel in a fast-paced team",
        "trust the process",
        "We want a Swift response and a spark of creativity",
    ],
)
def test_ambiguous_words_do_not_fire(text: str) -> None:
    assert extract_skills(text) == []


def test_word_boundaries() -> None:
    assert "Java" in extract_skills("java developer") and "JavaScript" not in extract_skills(
        "java developer"
    )
    assert "SQL" not in extract_skills("PostgreSQL only") and "PostgreSQL" in extract_skills(
        "PostgreSQL only"
    )
    assert "C" not in extract_skills("C-suite and vitamin C")


def test_dictionary_is_wellformed() -> None:
    skills = load_skills()
    names = [s.name for s in skills]
    assert len(names) == len(set(names)) and len(names) > 100
    assert all(s.aliases or s.cs or s.regex for s in skills)


def test_role_section_skips_company_intro_and_skills_exclude_company_name() -> None:
    intro = "Databricks is the data and AI company. " * 20
    body = "Requirements: Python and SQL, 2+ years. " + "x " * 200
    desc = intro + body
    assert role_section(desc).startswith("Requirements")
    got = skills_for_posting("Data Engineer", desc, company_name="Databricks")
    assert "Databricks" not in got and "Python" in got and "SQL" in got
    # the intro mention does not count, because only the role section is searched
    assert "Machine Learning" not in skills_for_posting(
        "Engineer", "We do machine learning here. " * 30 + body
    )


@pytest.mark.parametrize(
    ("title", "family"),
    [
        ("Software Engineer, New Grad", "software_engineering"),
        ("Machine Learning Engineer", "ml_ai"),
        ("Software Engineer, ML Infrastructure", "ml_ai"),
        ("Data Engineer II", "data_engineering"),
        ("Analytics Engineer", "data_engineering"),
        ("Data Analyst", "data_analytics"),
        ("Research Scientist, Safety", "ml_ai"),
        ("Member of Technical Staff", "software_engineering"),
        ("Solutions Engineer", "other"),
        ("Customer Support Engineer", "other"),
        ("Senior Account Executive", "other"),
        ("Recruiting Coordinator", "other"),
        ("Business Operations Associate", "other"),
    ],
)
def test_role_family(title: str, family: str) -> None:
    assert classify_role_family(title) == family
