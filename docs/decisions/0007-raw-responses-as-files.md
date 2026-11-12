# Raw API responses are stored as gzipped files, not in the database

**Status:** accepted

**Context:** Raw payloads (content=true) are large, and we need them to reproduce any normalized row.

**Decision:** Gzipped JSON under data/raw/<source>/<board>/<local-date>__<utc-time>Z.json.gz (gitignored). ingestion_runs stores the path, sha256 and HTTP status. Files older than RAW_RETENTION_DAYS (default 14) are pruned after each run and by make clean-raw. A board is fetched at most once per local day unless --force; if today's file exists but was never ingested (crash), its saved bytes are replayed instead of refetching.

**Alternatives:** JSONB column (queryable but bloats Postgres and backups).

**Consequences:** Reproducibility is limited to the retention window; normalized rows are the long-term record. A garbage or failed response is never saved, so it cannot become 'today's file'.
