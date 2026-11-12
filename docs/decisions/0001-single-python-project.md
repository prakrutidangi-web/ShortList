# Single root Python project managed by uv

**Status:** accepted

**Context:** API and ML code must share feature and embedding logic between training and serving.

**Decision:** One root pyproject.toml with packages shortlist_api and shortlist_ml, managed by uv with a committed uv.lock.

**Alternatives:** Separate projects per app (needs a shared library, slower iteration); Poetry or pip-tools.

**Consequences:** Heavy ML deps (torch etc.) will enter the API image unless split into dependency groups; revisit at Phase 2/5.
