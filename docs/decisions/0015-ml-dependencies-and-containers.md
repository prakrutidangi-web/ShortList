# Heavy ML dependencies live in an optional group; containers stay slim by default

**Status:** accepted

**Context:** torch + sentence-transformers add about 1 GB locally (the default Linux PyPI torch wheel adds multi-GB CUDA libraries). make check and CI must stay fast and must not need them.

**Decision:** pyproject has a dependency group 'ml' that uv does NOT install by default (default-groups = ['dev']); 'make install-ml' installs it. On Linux, torch resolves from the CPU-only PyTorch index (macOS uses PyPI Apple-Silicon wheels with MPS). CI and 'make check' use a deterministic hashing FakeEncoder (EMBEDDING_BACKEND=fake in tests) so the whole pipeline is tested with no torch; tests that need the real model are marked 'model' and run only via 'make test-model'. mypy ignores the optional modules. The default API container installs without the ml group; saving a profile there returns a clear 503 telling the user how to enable the model. An opt-in 'api-ml' compose service (profile 'ml', CPU only, own port 8002, model cache volume) is built with --build-arg WITH_ML=1. The recommended local path is 'make dev' (API native with the ml group), because Docker on macOS cannot use the Apple GPU.

**Alternatives:** Install everything everywhere (multi-GB default image, slow CI); a separate embedding microservice (out of scope: no microservices).

**Consequences:** Two encoders must stay behaviour-compatible: tests cover the pipeline with the fake, and the real-model tests check shape, normalisation and a semantic-ranking sanity case. The opt-in container image is slower than native.
