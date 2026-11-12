# Next.js App Router with pnpm; Python 3.12, Node 22

**Status:** accepted

**Context:** Need a typed, reproducible frontend toolchain.

**Decision:** Next.js 15 App Router, TypeScript, Tailwind, pnpm 9 with committed lockfile; Python 3.12 and Node 22 pinned in .python-version, .nvmrc and Docker images. The page fetches the API server-side to avoid CORS.

**Alternatives:** npm/yarn; Pages Router.

**Consequences:** Local Node may be newer than 22 (warnings possible); Docker and CI use 22.
