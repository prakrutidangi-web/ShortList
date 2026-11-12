# shortlist

Personalized ranking for new-grad and entry-level job postings: embedding retrieval, then a learned
(LightGBM LambdaMART) ranker. Rankings come from ML models, not LLM prompting.

**Status:** Phase 2 (baseline recommender). Ingestion, skills, embeddings, resume/profile parsing, filters, `/recommend`
and a simple feed UI exist. The ranking is a hand-weighted, **untuned** scorer; no evaluation has been run yet (Phase 3). Any numbers added here later
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
make reparse # re-derive rule-based fields (after changing normalization rules)
make report  # write docs/ingest-report.md (per-company counts + run stats)
make ingest  # fetch boards in companies.yaml (FORCE=1 to refetch today)
make clean-raw  # prune raw API files past RAW_RETENTION_DAYS (DRY=1 to preview)
```
Requires Docker, [uv](https://docs.astral.sh/uv/), Node 22, pnpm.

### Try the feed with your resume (Phase 2)
```
cp .env.example .env            # then adjust ports if 5433/8000 are taken
make up                         # or: docker compose up -d db
make install-ml                 # one-time: torch + sentence-transformers (~1 GB); not needed for make check
make migrate && make ingest     # postings (needs companies.yaml)
make enrich && make embed       # skills/role families, then embeddings (bge-small; uses the Apple GPU if available)
make dev                        # API on :8000 (with the ML stack) and web on :3000
```
Open http://localhost:3000/profile, upload a text-based PDF (or paste text), review the suggested skills, save, then open the Feed.
Your resume is parsed in memory and never stored. "Delete my profile data" removes everything derived from it.
The default Docker API image has no torch (saving a profile there returns a clear 503); see ADR 0015 for the opt-in `api-ml` image.

See `docs/architecture.md` and `docs/decisions/`.
