"""Curated-dictionary skill extraction and rule-based role family.

Both are HEURISTICS (ADR 0011): the dictionary is hand-written, so it misses skills it does not list and
can mis-fire on ambiguous words despite the case/context gating. Measured on a small hand-labeled sample
in docs/skills-eval.md.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

SKILLS_FILE = Path(__file__).with_name("skills.yaml")
ROLE_FAMILIES = ("software_engineering", "data_engineering", "ml_ai", "data_analytics", "other")

_LEFT = r"(?<![A-Za-z0-9_+#.])"
_RIGHT = r"(?![A-Za-z0-9_+#]|\.[A-Za-z0-9])"


@dataclass(frozen=True)
class Skill:
    name: str
    category: str
    aliases: tuple[str, ...] = ()
    cs: tuple[str, ...] = ()
    regex: tuple[str, ...] = ()


def load_skills(path: Path = SKILLS_FILE) -> list[Skill]:
    rows = yaml.safe_load(path.read_text())
    return [
        Skill(
            str(r["name"]), str(r["category"]), tuple(map(str, r.get("aliases", ()))),
            tuple(map(str, r.get("cs", ()))), tuple(map(str, r.get("regex", ()))),
        )
        for r in rows
    ]  # fmt: skip


def _wrap(s: str) -> str:
    return f"{_LEFT}{re.escape(s)}{_RIGHT}"


@lru_cache
def _compiled() -> tuple[tuple[Skill, re.Pattern[str]], ...]:
    out = []
    for sk in load_skills():
        parts: list[str] = []
        if sk.aliases:
            parts.append("(?i:" + "|".join(_wrap(a) for a in sk.aliases) + ")")
        if sk.cs:
            parts.append("(?:" + "|".join(_wrap(a) for a in sk.cs) + ")")
        if sk.regex:
            parts.append("(?i:" + "|".join(sk.regex) + ")")
        out.append((sk, re.compile("|".join(parts))))
    return tuple(out)


# Company intros are boilerplate ("Datadog is an observability platform..."). Everything from the first
# role/requirements marker on is the part that describes THIS job.
_ROLE_MARKER = re.compile(
    r"(about the role|the role|responsibilit|what you.?ll do|you will|what you.?ll be doing|"
    r"requirements|qualifications|what you bring|who you are|you have|what we.?re looking for|minimum)",
    re.I,
)


def role_section(description: str) -> str:
    flat = re.sub(r"\s+", " ", description).strip()
    m = _ROLE_MARKER.search(flat)
    return flat[m.start() :] if m and m.start() < len(flat) - 300 else flat


def skills_for_posting(title: str, description: str, company_name: str = "") -> list[str]:
    """Skills for one posting: title + role section only, minus a skill that is the company's own name
    (e.g. 'Databricks' in a Databricks posting)."""
    found = extract_skills(f"{title}\n{role_section(description)}")
    own = company_name.strip().lower()
    return [s for s in found if s.lower() != own]


def skill_names() -> list[str]:
    return [s.name for s in load_skills()]


def extract_skills(text: str) -> list[str]:
    """Canonical skill names found in `text`, in dictionary order (stable)."""
    return [sk.name for sk, pat in _compiled() if pat.search(text)]


# ---------------------------------------------------------------- role family
_NON_ENGINEERING = re.compile(
    r"\b(sales|solutions? (?:engineer|architect|consultant)|customer (?:engineer|success|support)|"
    r"support engineer|account (?:executive|manager)|field engineer|pre-?sales|technical account|"
    r"recruit\w*|marketing|legal|counsel|finance|accountant|hr\b|people\b|writer|designer)\b",
    re.I,
)
_ML = re.compile(
    r"\b(machine learning|ml\b|\bai\b|artificial intelligence|deep learning|nlp|computer vision|"
    r"research (?:scientist|engineer)|applied scientist|llm|genai|generative|data scientist|"
    r"model(?:ing)? engineer|research associate)\b",
    re.I,
)
_DATA_ENG = re.compile(
    r"\b(data engineer\w*|analytics engineer\w*|etl|data platform|data infrastructure|big data|"
    r"data pipeline\w*|database engineer|dba|data architect)\b",
    re.I,
)
_SWE = re.compile(
    r"\b(software|backend|back-end|frontend|front-end|full[- ]?stack|web developer|mobile|ios|android|"
    r"site reliability|sre|devops|platform engineer|infrastructure engineer|systems engineer|"
    r"security engineer|firmware|embedded|sdet|qa engineer|developer|programmer|swe|"
    r"member of technical staff|engineer)\b",
    re.I,
)
_ANALYTICS = re.compile(
    r"\b(data analyst|business analyst|business intelligence|bi analyst|analytics|analyst)\b", re.I
)


def classify_role_family(title: str) -> str:
    """Rule-based role family from the TITLE only (software_engineering | data_engineering | ml_ai |
    data_analytics | other). Order: non-engineering words -> other; ML/AI; data engineering; software;
    analytics. A title with both ML and software words (e.g. 'Software Engineer, ML Infrastructure')
    is ml_ai. 'Data scientist' is grouped under ml_ai (a judgment call; many are analytics roles)."""
    if _NON_ENGINEERING.search(title) and not re.search(r"\bsoftware\b", title, re.I):
        return "other"
    if _ML.search(title):
        return "ml_ai"
    if _DATA_ENG.search(title):
        return "data_engineering"
    if _SWE.search(title):
        return "software_engineering"
    if _ANALYTICS.search(title):
        return "data_analytics"
    return "other"
