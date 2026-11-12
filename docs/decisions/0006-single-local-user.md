# Single local user keyed by user_id until Phase 5

**Status:** accepted

**Context:** Accounts are Phase 5, but per-user splits and delete-my-data need user_id from the start.

**Decision:** Schema keyed by user_id; a default local user until real auth exists (to be reconfirmed in the Phase 1 plan).

**Alternatives:** Add auth first (large detour); no user_id (breaks per-user evaluation splits).

**Consequences:** No real access control before Phase 5; do not expose a deployment before then.
