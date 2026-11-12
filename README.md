# shortlist

Personalized ranking for new-grad and entry-level job postings: embedding retrieval, then a learned
(LightGBM LambdaMART) ranker. Rankings come from ML models, not LLM prompting.

**Status:** Phase 1 (ingestion). Greenhouse + Lever ingestion exists; no ML or metrics yet. Any numbers added here later
will come from `make eval`.

## Quickstart
```
cp .env.example .env
make help
make up      # Postgres (pgvector) + API + web in Docker
make dev     # DB in Docker, API + web natively with hot reload
make check   # lint + typecheck + tests
make migrate # apply DB migrations (db must be up)
make verify-companies  # check companies.candidates.yaml against live APIs -> companies.yaml
make ingest  # fetch boards in companies.yaml (FORCE=1 to refetch today)
make clean-raw  # prune raw API files past RAW_RETENTION_DAYS (DRY=1 to preview)
```
Requires Docker, [uv](https://docs.astral.sh/uv/), Node 22, pnpm.

See `docs/architecture.md` and `docs/decisions/`.
