# Skill extraction: hand-labeled evaluation (small sample)

Per-row detail: `skills-labels.csv`. Date: 2026-11-12.

## Method and limits
- **30 postings** (seed 11): 10 each from `software_engineering`, `data_engineering`, `ml_ai` among open postings with at least 1,500 characters.
- **The labels are mine (the assistant's)**, written from each posting's title and the first ~880 characters of its role section,
  **before** I ran the extractor on them. They are not independent human labels; please review `skills-labels.csv` and overrule rows.
- I labeled technologies, tools, frameworks, methods and domains that a candidate would list as skills, not soft skills. A skill the dictionary
  has no entry for is labeled `OOD:<name>` (out of dictionary) and counts only against the "all skills" recall.
- The extractor was run through the production function (`skills_for_posting`: title + role section, minus the posting company's own name).
  It saw only the same ~880-character excerpt, so this measures behaviour on the opening of the role section, not whole postings.
- 30 postings / 63 labeled skills is small. Intervals are 95% Wilson intervals over skills treated as independent, which they are not;
  treat them as rough.

## Results
| Metric | Value |
|---|---|
| Skills extracted | 48 |
| Precision | **40 / 48 = 83%** [70-91%] |
| Recall, skills the dictionary has an entry for | 40 / 51 = 78% [65-88%] |
| Recall, all labeled skills incl. out-of-dictionary (12) | 40 / 63 = 63% [51-74%] |
| Postings with no labeled skill / with no extracted skill | 6 / 7 |

## Failure modes seen (NOT fixed; they are measured on this same sample, so fixing them here would be tuning on the eval set)
- **False positives (8):** `A/B Testing` fires on the word "experimentation" in generic sentences (3); `Machine Learning` fires on "ML engineers" as an
  audience (2); `Robotics` on a domain list; `CI/CD` on "continuous delivery" in prose; `Git` on "GitLab" in a GitLab posting.
- **Misses in the dictionary (11):** `Distributed Systems` (phrased as "distributed system" singular / "multithreaded distributed system"),
  `Unit Testing` ("writing tests"), `Data Modeling` ("design data schemas"), `Iceberg`/`Hive` when listed in a parenthesised list, `Cybersecurity`
  ("information security").
- **Out-of-dictionary skills (12)** such as NetSuite, LanceDB, Celeborn, S3, "AI agents", "LLM evals", "diffusion models", RLHF: the dictionary is
  138 hand-written entries aimed at software/data/ML roles.
- Generic skills (Observability, Networking, Machine Learning) are very common in the full corpus; this sample was too small to tell how much of that is noise.

## Proposed fixes (need your OK; re-measure on a NEW sample, not this one)
1. Drop or gate the bare "experimentation" alias; gate "ML" to skill contexts rather than "ML engineers".
2. Add singular/plural and "writing tests" style variants; add a few missing entries (S3, NetSuite, RLHF, AI agents, LLM evals).
3. Exclude skill names that are substrings of the company name (Git/GitLab).
