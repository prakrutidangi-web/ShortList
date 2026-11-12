# Heuristic audit: how far to trust the rule-based fields

Date: 2026-11-12. Rules audited: the Phase 1 rules **as shipped, with no tuning after seeing the sample**.
Data: 8,634 open Greenhouse postings from 38 company boards (first ingest). Lever was not audited
(no Lever board is in `companies.yaml` yet).

## Method and its limits
- Seeded random sample (seed 42): **25 postings the rules flagged `is_entry_level`** (to estimate the flag's
  precision) and **25 they did not** (a rough check for misses). Row-level data: `heuristic-audit-sample.csv`.
- The judgments are **mine (the assistant's), made from the title plus the years/sponsorship evidence the rules
  saw**; they are not an independent human labeling. Please eyeball the CSV and overrule any row.
- "Entry-level" here means: a new-grad or 0-1 year candidate could reasonably apply. Role family is ignored
  (a Recruiting Coordinator can be entry-level; it is just not a target role).
- n = 25 per group is small; intervals below are 95% Wilson intervals and are wide.
- The sample is stratified by the flag, so the precision figure describes flagged postings, and the
  "miss" check cannot measure recall well: truly entry-level postings are rare among unflagged ones.

## The entry-level flag (`is_entry_level`): do not trust it yet
Population: 503 of 8,634 postings (5.8%) are flagged. **Only 80 of those come from a title keyword**
(new grad, early career, junior, entry level, "Engineer I", ...). **The other 423 come from the years rule alone**
(`years_min <= 2`: 8 with 0, 139 with 1, 276 with 2).

| Precision of the flag (25 flagged postings) | Count | Share | 95% CI |
|---|---|---|---|
| Clearly entry-level | 2 | 8% | 2-25% |
| Clearly or probably entry-level | 7 | 28% | 14-48% |
| Including borderline (1-3 yrs) | 11 | 44% | 27-63% |
| Wrong | 14 | 56% | |

By path: the **title-keyword path was 2 right, 1 wrong** (too few to estimate; the wrong one was
"[Junior / Senior / Staff] Software Engineer"). The **years-only path was 0 clearly right of 22**: 5 probably OK,
4 borderline, 13 wrong (mid-level engineers with "2+ years", account executives, a "Supervisor", Level II roles).

Unflagged side: **0 of 25** were clear misses (3 had no level signal at all, which rules cannot resolve). That bounds
the miss rate among unflagged postings below roughly 13%, but see the limit above.

**Practical reading today:** treat title-keyword flags as plausible and years-only flags as noise. Do not use
`is_entry_level` as a hard filter or as a trusted training label. `seniority = senior` looked reliable in this
sample (every senior/staff/lead/director title I checked was right).

### Causes (all visible in the CSV)
1. **`years_min` takes the minimum of all "N years ... experience" mentions.** Postings list several
   requirements, so the minimum is usually the least informative one (e.g. "4+ years ... 2+ years" gives 2; "5+ ... 2+" gives 2;
   "12+ ... 3+ years leadership" gives 3). 8 of the 50 rows have a clearly misleading `years_min`.
2. **The `years_min <= 2` threshold is too generous** for a new-grad target; 2 years of experience is not entry-level.
3. Level suffixes are only recognised for engineer/developer/scientist/analyst titles, and only as "I"/"II"
   (a "Specialist ll" written with lowercase L's was missed).
4. A title that lists several levels ("Junior / Senior / Staff") fires the `junior` keyword.

## Location parsing
Over all 50 rows: 34 fine, **7 wrong** (14%), **9 with no country** (18%).
- Wrong examples: "N/A", "Distributed", "IN-Bengaluru" and "Washington DC metro area" kept as the city; a comma-joined list
  of several locations mixing city and region from different places; "Remote-Friendly" parsed as a city.
- Population-level gaps (first ingest, 8,634 postings): **country is NULL for 2,102 (24%)**. It is concentrated by
  board, because boards format location differently: Cloudflare sends only a work mode ("Hybrid", "Distributed",
  "In-Office") for 478 of 481 postings, so there is no place at all; Vercel sends "Hybrid - San Francisco" and
  Together AI/Asana send bare city names (no country inferred); Dropbox sends "Remote - US: Select locations".
- Consequence: **do not use `country` alone for location matching.** Use `city`/`region`/`location_raw` and `is_remote`.
  `is_remote` is True for 315 of the NULL-country rows.
- Only the first location of a multi-location string is parsed; `location_raw` keeps them all.

## Sponsorship flag
Values in the population: `sponsors` 684, `restricted` 71, `unknown` 7,879. Spot checks: the explicit "visa sponsorship is not
available" / "not eligible for immigration sponsorship" cases were flagged `restricted` correctly (2 of 2 in the sample), and
export-control boilerplate ("... without sponsorship for an export license") was correctly left `unknown`.
Two known weaknesses, both about hedged wording:
- **Anthropic: 670 of the 684 `sponsors` flags.** The text says "We do sponsor visas! However, we aren't able to
  successfully sponsor visas for every role and every candidate." Flagging that `sponsors` is generous; it is really "sometimes".
- **Roblox: 275 postings left `unknown`** that say the company "may not be able to employ candidates ... who have United States
  work authorization related to certain U.S. visa categories, or support future H-1B sponsorship at this time". That is hedged,
  but a visa-holder would likely want the warning. Under the conservative rule it stays `unknown`.
Other `unknown` postings that mention sponsorship were mostly non-visa uses ("executive sponsorship", event sponsorships).
I did not measure recall for the other 7,500+ unknown postings beyond this scan.

## Other observations
- 30 postings are reposts (same company/title/location/description under a new id) and 22 dedup keys have more than one member, from
  the first ingest alone. `closed` is 0 and `guarded` is 0 because there is no earlier snapshot to compare with yet.
- `first_published` is present on every Greenhouse posting but 502 of 8,634 are more than a year old (evergreen listings).

## Proposed fixes (NOT applied; they need your decision)
Because these come from looking at this sample, I would apply them only with your approval and then re-measure on a **fresh
sample (a different seed)**, never on this one, and report before/after plainly.
1. `years_min`: take the **maximum** (or the first mention) instead of the minimum, so the headline requirement wins.
2. Entry rule: require `years_min <= 1` (0-1 years) for the years path; keep title keywords as they are.
3. Recognise `II/III/IV/2/3` level suffixes for any title (including lowercase "ll"); ignore title keywords inside multi-level
   brackets such as "[Junior / Senior / Staff]".
4. Location: drop junk tokens ("N/A", "Distributed", "In-Office", "metro area"), strip ": Select locations", take only the first
   city when a comma list mixes several, and consider a small city-to-country lookup for common hubs.
5. Sponsorship: decide whether hedged "may not be able to ... H-1B sponsorship" (Roblox) should be `restricted`, and whether
   "We do sponsor visas! However ... not for every role" (Anthropic) should be `sponsors` or `unknown`.
