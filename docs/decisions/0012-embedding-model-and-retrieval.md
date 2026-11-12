# Embeddings: bge-small-en-v1.5, exact pgvector search, no ANN index (yet)

**Status:** accepted

**Context:** Stage 1 needs a small, CPU/laptop-friendly sentence embedding model and a vector store. There are no relevance labels yet, so the model choice cannot be validated empirically in Phase 2.

**Decision:** BAAI/bge-small-en-v1.5 (384-d, 512-token context), chosen on priors: published retrieval benchmarks (not re-verified by me) put it above all-MiniLM-L6-v2, and its 512-token window reads more of each posting than MiniLM's 256. Queries get bge's documented instruction prefix; documents do not. The embedded text is a compact 'posting document' (title, role family, level, up to 15 skills, then up to 1,500 characters starting at the first role/requirements marker, to skip company boilerplate). Vectors live in pgvector (vector(384)) with an EXACT scan: ~10.5k vectors take milliseconds and have perfect recall, so no HNSW/IVFFlat index until latency measurements demand one. Open postings only; re-embedded when the document text or model changes (sha256). Device: auto-selects the Apple GPU (MPS), CPU otherwise. MEASURED on this Mac (M-series, 2026-11-12): 256 posting documents, batch 32, warm: CPU 54.1 docs/s vs MPS 150.3 docs/s (2.8x), so MPS is used. Full run: 10,549 open postings embedded in 129.0 s (81.8 postings/s end to end, including database writes); model load 3.1 s; a second run re-embedded 0 of 10,549. End-to-end /recommend latency over 60 varied calls on localhost: p50 46 ms, p95 54 ms.

**Alternatives:** all-MiniLM-L6-v2 (smaller, faster, truncates earlier), e5-small-v2; chunking+pooling long postings (more code, unproven benefit); HNSW now (premature and approximate).

**Consequences:** The model choice is a prior, not a result. Phase 3 re-compares models on labeled data with Recall@50/NDCG. The posting document is a heuristic that throws away most of a long description. The model is a ~130 MB download on first use (public weights; no user data leaves the machine).
