# Ingestion runs as a CLI command, scheduled externally

**Status:** accepted

**Context:** Daily refresh is needed; Redis/queues are out of scope until a measured need.

**Decision:** A CLI entry point (python -m shortlist_ml.ingest) triggered by cron or a compose service.

**Alternatives:** APScheduler inside the API process (couples job lifecycle to the web process).

**Consequences:** Easy to test and run in CI; scheduling lives outside the app.
