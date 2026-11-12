# Rule-based fields are soft signals with evidence, never gates

**Status:** accepted

**Context:** The Phase 1 audit (docs/heuristic-audit.md) showed the entry-level flag, the location parse and the sponsorship flag are heuristics with real error rates, and several boards give no usable location at all.

**Decision:** (1) is_entry_level stays, but with entry_evidence (title_keyword | phrase | years) and the matched text; Phase 2+ uses it as a ranker feature and a user-toggleable UI filter, and never hard-filters the feed on it. (2) An unknown country is unknown, not non-US: no posting is dropped, hidden or down-ranked only because city/region/country is NULL; location_raw is always stored and shown. (3) sponsorship is restricted | offered | unclear with the matched sentence stored (hedged wording is unclear plus its snippet); it is a warning only. (4) Rule changes made after looking at an audit sample are re-measured on a new random sample, and an improvement is claimed only if the confidence intervals separate.

**Alternatives:** Hard filters (fast but silently hide good postings when a rule is wrong); a learned classifier now (no labels yet).

**Consequences:** The feed will contain noisy entry-level labels until the Phase 3 labeling data exists; ranking features must use the evidence type, not just the boolean. Postings with unknown location rely on is_remote and the raw string.
