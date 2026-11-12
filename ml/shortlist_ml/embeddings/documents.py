from shortlist_ml.skills.extract import role_section

# bge-small reads up to 512 tokens (~2,000 characters). Median postings are far longer and the first
# paragraphs are mostly company boilerplate, so the document starts at the role section and is capped.
# (Heuristic; revisit with labels in Phase 3.)
DESC_CHARS = 1500


def posting_document(
    title: str, role_family: str | None, seniority: str, skills: list[str], description: str
) -> str:
    body = role_section(description)
    head = f"{title}\nRole: {role_family or 'other'}; level: {seniority}"
    if skills:
        head += "\nSkills: " + ", ".join(skills[:15])
    return f"{head}\n{body[:DESC_CHARS]}"
