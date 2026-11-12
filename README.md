# shortlist

Personalized ranking for new-grad and entry-level job postings: embedding retrieval, then a learned
(LightGBM LambdaMART) ranker. Rankings come from ML models, not LLM prompting.

**Status:** Phase 0 (scaffold). No ML, ingestion, or metrics yet. Any numbers added here later
will come from `make eval`.

## Quickstart
```
cp .env.example .env
make help
make up      # Postgres (pgvector) + API + web in Docker
make dev     # DB in Docker, API + web natively with hot reload
make check   # lint + typecheck + tests
```
Requires Docker, [uv](https://docs.astral.sh/uv/), Node 22, pnpm.

See `docs/architecture.md` and `docs/decisions/`.
