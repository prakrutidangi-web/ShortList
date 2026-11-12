# companies.yaml contains only verified boards

**Status:** accepted

**Context:** Board tokens guessed from memory are often wrong, and many companies are not on Greenhouse/Lever at all.

**Decision:** Candidates live in companies.candidates.yaml. make verify-companies calls each live endpoint (1 req/s), writes companies.yaml with only boards returning HTTP 200 and at least one job, and writes docs/company-verification.md with every failure and reason. Companies on unsupported ATSs are listed as not attempted and never scraped.

**Alternatives:** Hand-edit companies.yaml (invites unverified tokens).

**Consequences:** A board with zero jobs today is excluded until a re-verify; re-run the command to refresh the list.
