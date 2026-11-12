# Build context is the repo root (pyproject.toml and uv.lock live there).
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_CACHE=1 PATH="/app/.venv/bin:$PATH"

ARG WITH_ML=0
COPY pyproject.toml uv.lock .python-version ./
COPY apps/api/shortlist_api apps/api/shortlist_api
COPY ml/shortlist_ml ml/shortlist_ml
# Default image is slim: no torch. `--build-arg WITH_ML=1` adds the optional ml group (CPU-only torch on Linux).
RUN if [ "$WITH_ML" = "1" ]; then uv sync --frozen --no-dev --group ml; else uv sync --frozen --no-dev; fi

EXPOSE 8000
CMD ["uvicorn", "shortlist_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
