"""Turn resume text into SUGGESTED profile fields, and profile fields into the document that is embedded.

Privacy (ADR 0013): names, emails, phone numbers and addresses are never extracted. Only dictionary skills
and a graduation date are suggested; the user confirms and edits everything before anything is stored.
"""

import re
from dataclasses import dataclass
from datetime import date

from shortlist_ml.skills.extract import extract_skills

ROLE_LABELS = {
    "software_engineering": "software engineering",
    "data_engineering": "data engineering",
    "ml_ai": "machine learning and AI",
    "data_analytics": "data analytics",
}
TARGETABLE_ROLES = tuple(ROLE_LABELS)

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}
_GRAD = re.compile(
    r"(?:expected\s+)?(?:graduation|graduating|graduate|grad\.?|degree)\b[^\n]{0,40}?"
    r"(?:(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*,?\s*)?(20[2-3]\d)",
    re.I,
)
_CLASS_OF = re.compile(r"class of\s+(20[2-3]\d)", re.I)
_EXPECTED = re.compile(
    r"(?:expected|anticipated|exp\.?)\s*(?:in\s+)?(?:(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*,?\s*)?(20[2-3]\d)",
    re.I,
)


@dataclass(frozen=True)
class ProfileSuggestion:
    skills: list[str]
    grad_date: date | None
    grad_date_evidence: str | None  # the matched snippet, so the user can check it


def suggest_grad_date(text: str) -> tuple[date | None, str | None]:
    """Best guess at the graduation month/year. No month => June (approximate; the user edits it)."""
    for pat in (_EXPECTED, _GRAD):
        m = pat.search(text)
        if m:
            month = _MONTHS.get((m.group(1) or "").lower()[:3], 6)
            return date(int(m.group(2)), month, 1), m.group(0).strip()[:60]
    m2 = _CLASS_OF.search(text)
    if m2:
        return date(int(m2.group(1)), 6, 1), m2.group(0)
    return None, None


def suggest_from_text(text: str) -> ProfileSuggestion:
    gd, ev = suggest_grad_date(text)
    return ProfileSuggestion(skills=extract_skills(text), grad_date=gd, grad_date_evidence=ev)


def profile_document(
    skills: list[str], target_roles: list[str], about_text: str | None, grad_date: date | None
) -> str:
    """The EXACT text that gets embedded for retrieval; the UI shows it to the user before saving."""
    roles = ", ".join(ROLE_LABELS.get(r, r) for r in target_roles) or "software, data and AI roles"
    lines = [f"New graduate seeking entry-level roles in {roles}."]
    if skills:
        lines.append("Skills: " + ", ".join(skills[:40]) + ".")
    if grad_date:
        lines.append(f"Graduating {grad_date:%B %Y}.")
    if about_text and about_text.strip():
        lines.append(re.sub(r"\s+", " ", about_text.strip())[:1500])
    return "\n".join(lines)
