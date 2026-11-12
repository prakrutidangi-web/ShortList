# Edit vs repost vs closed semantics for postings

**Status:** accepted

**Context:** Time-based train/eval splits will use first_seen_at, last_seen_at and closed_at, so their meaning must be exact. Edited postings must not be mistaken for reposts, and API hiccups must not mass-close postings.

**Decision:** Same (company, source, external_id) with a changed content_hash is an EDIT: update in place, set updated_at. A new external_id whose dedup_key (normalized title, location, description hash, within the company) matches an existing posting is a REPOST and gets canonical_id pointing at the group's earliest member; the serving view returns one open member per group. A posting absent from a successful snapshot gets closed_at, unless the snapshot is empty or has more than 50% fewer postings than were open: then nothing is closed and the run is marked guarded. Failed fetches never close anything. Reappearing postings are reopened. first_seen_at is set once; last_seen_at advances on every sighting.

**Alternatives:** Fuzzy near-duplicate matching (no evidence yet it is needed, risk of merging distinct roles); closing on any absence (silently mass-closes on API errors).

**Consequences:** A real mass layoff of a company's openings is held back by the guard until the next run's baseline shifts or someone investigates; the 50% threshold is a judgement call, revisit with real data.
