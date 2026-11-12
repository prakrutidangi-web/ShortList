# Rule-based normalization, conservative sponsorship flag

**Status:** accepted

**Context:** We need seniority, location and work-authorization signals now, before there is training data.

**Decision:** Regex/keyword heuristics for years required, seniority (title keywords beat years), location parsing (first location only is parsed; raw text kept) and a sponsorship flag with values restricted | sponsors | unknown. The flag returns unknown whenever unsure (ambiguous wording, contradictory text, unrelated uses of the word sponsor) and is shown as a warning, never used to filter.

**Alternatives:** Learned classifiers (no labels yet); LLM extraction (not allowed in the ranking path and unnecessary here).

**Consequences:** Known failure modes are documented next to each function and covered by positive and negative tests; expect misses (for example unusual phrasings) rather than false 'restricted' labels.

**Update (2026-11-12, after the first live ingest):** location parsing was rewritten after real data showed state names, `USA`, `NY \u2022 United States` and similar landing in `country` (country is now ISO alpha-2, region a US/CA abbreviation). Because ingest does not refresh derived fields when posting text is unchanged, `make reparse` re-derives them from stored text without touching timestamps. A sampled audit of the shipped rules is in `docs/heuristic-audit.md`: the years-based entry-level flag is not trustworthy yet.
