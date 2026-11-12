# Architecture (planned; only the boxes marked ✅ exist in Phase 0)

```
 ATS APIs (Greenhouse / Lever / Ashby)
        │  daily CLI job (cron)                         [Phase 1]
        ▼
  raw JSON store ──► normalizer ──► Postgres (postings, skills, embeddings via pgvector)
                                          │
        user profile/resume (derived) ────┤
                                          ▼
              Stage 1: embedding (+BM25) retrieval  [Phase 2]
                                          ▼
              Stage 2: LightGBM lambdarank           [Phase 4]
                                          ▼
   ✅ FastAPI (/health) ──► /recommend ──► ✅ Next.js UI ──► feedback + impression logs [Phase 3]
```

Python code lives in one package set (`shortlist_api`, `shortlist_ml`) so training and serving share
feature code. Rankings come from ML models only; no LLM in the ranking path.
