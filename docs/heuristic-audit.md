# Heuristic audit: how far to trust the rule-based fields

Two audit rounds, 2026-11-12. Row-level data and my per-row judgments:
`heuristic-audit-sample.csv` (round 1, dev set) and `heuristic-audit-fresh-sample.csv` (round 2, fresh set).

## Method and its limits (read first)
- **Round 1 (DEV set):** seeded random sample (seed 42) of the first ingest (8,634 Greenhouse postings): 25 postings the
  original rules flagged `is_entry_level` and 25 they did not. I changed the rules after reading it, so it is a dev set.
- **Round 2 (FRESH set):** a new seeded sample (seed 2025) of the current 10,549 open postings (Greenhouse + Lever), drawn
  after the rule changes: 25 flagged and 25 unflagged under the new rules. **No rule was tuned against it.**
- Judgments are **mine (the assistant's)**, from the title plus the evidence the rules recorded; they are not independent.
  In round 2 I could see which rule fired while judging, which may bias me toward the rule's answer. Please eyeball the CSVs
  and overrule rows; the numbers below move with your judgment.
- "Entry-level" = a new grad or 0-1 year candidate could reasonably apply. Role family is ignored.
  Categories: `correct` (explicit entry-level), `probably-ok`, `borderline` (needs ~1-3 yrs or ambiguous), `wrong`.
  The `wrong` count is the least subjective; the `borderline` boundary is a judgment call.
- n = 25 per group, 95% Wilson intervals, so every interval is wide. The two samples use different sampling frames (old vs new
  rule, partly different postings), so the comparison is indicative, not a controlled experiment.

## What changed between rounds (rules)
1. `years_min` is now the **maximum** of the "N years ... experience" lower bounds (was the minimum).
2. The years-only entry rule is now **<= 1 year** (was <= 2); 2-5 years is `mid`, 6+ is `senior`.
3. Level suffixes (I, II, III, IV, 1-4, lowercase "ll") are recognised for any title: I is entry-level, II mid, III+ senior.
   A title containing both an entry and a senior keyword ("[Junior / Senior / Staff]") is `unknown`, never entry-level.
4. **Explicit phrases in the description** ("new grad", "university graduate", "recent graduate", "early career",
   "class of 20XX") are their own evidence type (`phrase`), used when `years_min` is absent or <= 2.
5. Every entry-level flag now stores `entry_evidence` (`title_keyword` | `phrase` | `years`) and the matched text.
   It is a **soft signal**: kept as a column/feature and a user-toggleable filter, never a gate (ADR 0011).
6. Location cleanup: junk tokens ("N/A", "Distributed", "In-Office", "metro area", "Remote-Friendly"), ": Select locations"
   suffixes, "IN-Bengaluru" style prefixes, mixed multi-location comma lists, DC. Unknown stays NULL.
7. Sponsorship is now `restricted | offered | unclear` with the matched sentence stored (`sponsorship_evidence`).
   Hedged wording is `unclear` plus its sentence. After round 2, a verb-form bug was fixed (below).

## Entry-level precision: before vs after

| Precision of the flag (25 flagged each) | BEFORE: dev set, old rules | AFTER: fresh set, new rules | Verdict |
|---|---|---|---|
| Clearly entry-level | 2/25 = 8% [2-25%] | 9/25 = 36% [20-55%] | CIs overlap slightly: higher point estimate, **not a claimable improvement on its own** (Fisher p = 0.04, indicative only) |
| Likely (correct + probably-ok) | 7/25 = 28% [14-48%] | 17/25 = 68% [48-83%] | CIs barely separate (Fisher p = 0.01): an improvement, with a wide margin of error |
| Lenient (+ borderline) | 11/25 = 44% [27-63%] | 24/25 = 96% [80-99%] | CIs clearly separate (p = 0.0001) |
| **Clearly wrong** | **14/25 = 56%** | **1/25 = 4%** | the most objective comparison |

How the new rules did on the dev set they were tuned on (optimistic by construction): 8 postings flagged, 2 correct,
4 probably-ok, 2 borderline, 0 wrong. They also **stopped flagging 3 postings I had judged plausible** (a 2-year SWE, a 2-year
coordinator, a 1-2 year analyst), so the stricter threshold trades recall for precision. I did not measure recall beyond the
unflagged samples below.

By rule that fired (fresh set, small n):
- `title_keyword`: 9 of 9 correct. Trustworthy.
- `years` (<= 1 year): 12 flagged, 7 probably-ok, 5 borderline, 0 wrong. Plausible but not certain; these are mostly
  coordinator/BDR/associate-type roles.
- `phrase`: 4 flagged, 1 probably-ok, 2 borderline, **1 wrong** (a Level II engineer whose description mentions "early-career").
  The weakest evidence; do not trust it alone.

Unflagged side: **0 of 25** were clear misses in either round (Wilson upper bound ~13% for the miss rate among unflagged postings).
This cannot measure recall well: truly entry-level postings are rare among the unflagged.

**Population effect:** entry-level flags are now **335 of 10,549 open postings (3.2%)**: 165 `title_keyword`, 26 `phrase`, 144 `years`.
On the same Greenhouse-only population as the first ingest it is 197 of 8,634 (2.3%), down from 503 (5.8%).

**Reading:** treat `is_entry_level` as a decent *ranking feature* when the evidence is `title_keyword` (strong) or `years`
(moderate), and be skeptical of `phrase`. Use the evidence type as a separate feature, and keep the UI filter optional. It is
still not accurate enough to gate anything.

## Gaps found by the fresh set (NOT fixed; changing them needs a third sample)
1. **Level suffix hidden by " - " / en-dash separators.** "Power System - High-Voltage Test Engineer II - Electric Power" was
   flagged entry via the "early-career" phrase although it is Level II; "Software Engineer II - EDR Workflows" got seniority
   `unknown` instead of `mid` (correctly unflagged, wrongly labelled). The suffix detector only splits on commas.
2. **"Region - City" location formats** (Veeva: "Poland - Warsaw", "New Jersey - Lyndhurst", "Massachusetts - Boston"), "USA - Austin (dbt)"
   and office codes ("San Francisco - SF9") are kept whole as the city.
3. The `phrase` rule fires on ambient wording ("early-career researchers") for senior-ish roles.

## Location parsing (fresh set, 50 rows)
30 fine, **11 with no country by design** (bare city such as "Chicago", or only a work mode such as "Hybrid"), **9 wrong (18%)**.
Seven of the nine are the "Region - City" pattern above. Round 1 had 7 of 50 wrong (14%) and the rules fixed all seven, but the
fresh data brought a new pattern, so **location accuracy did not improve overall** (intervals overlap heavily).
Population: country is NULL for 1,875 of 10,549 open postings (18%); Cloudflare's feed gives only "Hybrid/Distributed/In-Office"
for 478 of 481 postings (no place at all).
**Policy (ADR 0011):** unknown country is *unknown*, not non-US. No posting is dropped or deprioritised for a NULL country; the raw
location string is always stored and shown. Use `city`/`region`/`location_raw`/`is_remote` for matching, and `country` only when present.

## Sponsorship flag
Population (after the fix below): `restricted` 95, `offered` 10, `unclear` 10,444 (947 of those carry a sentence of evidence).
- `unclear` with evidence is the hedged wording: Anthropic (670 postings; "We do sponsor visas! However, we aren't able to
  successfully sponsor visas for every role and every candidate."), Roblox (275; "may not be able to employ candidates ... support
  future H-1B sponsorship at this time") and MongoDB ("Company sponsorship may be available ... certain roles").
- All 10 `offered` rows are one Affirm role: "We are able to offer visa sponsorship for this role, but do require that someone is
  based in Spain" (a real but location-conditional offer).
- `restricted` includes explicit "no sponsorship" statements and US-citizenship requirements (GitLab, Samsara, Palantir); the
  evidence sentence is stored so the UI can show it. I read ~16 restricted/offered evidence strings and they looked right; this is
  a spot check, **not a measured accuracy**. The fresh sample had almost no non-`unclear` rows, so it cannot measure sponsorship.
- **Bug found and fixed after round 2:** "We do not sponsor visas for Fellows." (Scale AI) was labelled `offered` because only
  the noun form ("visa sponsorship") was recognised as a restriction. The verb form is now `restricted` (5 postings changed;
  tests added). This is a sponsorship rule, so it does not affect the entry-level samples.
- Evidence sentences can include neighbouring bullet text, because the flattened description has no sentence breaks (capped to ~300 chars).

## Not measured / caveats
- Lever: only 5 boards (1,915 postings) are in the data; the audit samples include Lever rows but too few to say anything Lever-specific.
- Recall of the sponsorship flag over the ~10,000 `unclear` postings is unmeasured beyond a keyword scan for sentences containing
  "visa/sponsorship/immigration" (which found the hedged Anthropic/Roblox wording, the verb-form bug, and otherwise
  non-visa "executive sponsorship" uses).
- All judgments are mine.
