# mypy strict, CI without Docker for unit tests

**Status:** accepted

**Context:** Quality bar for a portfolio project, and fast CI.

**Decision:** mypy strict with per-module relaxations only for untyped third-party libs; unit tests run without a DB; DB tests are marked db and run against a pgvector service container.

**Alternatives:** Looser typing; Docker Compose in CI.

**Consequences:** Some friction adding ML libraries later; CI stays fast.
