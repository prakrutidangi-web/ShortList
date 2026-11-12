.DEFAULT_GOAL := help
-include .env
export

.PHONY: help up down logs dev install migrate ingest verify-companies reparse report clean-raw lint fmt typecheck test test-db check eval

help: ## Show available targets
	@grep -hE '^[a-z-]+:.*## ' Makefile |awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

up: ## Start everything (db, api, web) in Docker
	docker compose up -d --build

down: ## Stop the Docker stack (data volume is kept)
	docker compose down

logs: ## Tail Docker logs
	docker compose logs -f

dev: ## DB in Docker; API + web natively with hot reload (Ctrl-C stops both)
	docker compose up -d db
	@trap 'kill 0' INT TERM; \
	uv run uvicorn shortlist_api.main:app --reload --app-dir apps/api --port $${API_HOST_PORT:-8000} & \
	NEXT_PUBLIC_API_URL=http://localhost:$${API_HOST_PORT:-8000} pnpm --dir apps/web dev --port $${WEB_HOST_PORT:-3000} & \
	wait

install: ## Install Python and web dependencies
	uv sync
	pnpm --dir apps/web install --frozen-lockfile

migrate: ## Apply database migrations (needs the db up: `make up` or `docker compose up -d db`)
	uv run alembic upgrade head

ingest: ## Fetch boards in companies.yaml into the database (FORCE=1 to refetch today)
	uv run python -m shortlist_ml.ingest run $(if $(FORCE),--force,)

verify-companies: ## Check companies.candidates.yaml against live APIs; writes companies.yaml + docs/company-verification.md
	uv run python -m shortlist_ml.ingest verify-companies

reparse: ## Re-derive rule-based fields (location, seniority, ...) for stored postings after a rule change
	uv run python -m shortlist_ml.ingest reparse

report: ## Write docs/ingest-report.md (per-company counts + run stats); regenerate after changes
	uv run python -m shortlist_ml.ingest report

clean-raw: ## Delete raw API files older than RAW_RETENTION_DAYS (DRY=1 to preview)
	uv run python -m shortlist_ml.ingest clean-raw $(if $(DRY),--dry-run,)

lint: ## ruff (lint + format check) and eslint
	uv run ruff check .
	uv run ruff format --check .
	pnpm --dir apps/web lint

fmt: ## Auto-format and fix Python
	uv run ruff check --fix .
	uv run ruff format .

typecheck: ## mypy (strict) and tsc
	uv run mypy
	pnpm --dir apps/web typecheck

test: ## Unit tests (no Docker or DB needed)
	uv run pytest -m "not db"

test-db: ## Tests that need Postgres (run `make up` first; uses DATABASE_URL from .env)
	RUN_DB_TESTS=1 uv run pytest -m db

check: lint typecheck test ## lint + typecheck + test

eval: ## Reproduce all evaluation numbers (not implemented until Phase 3)
	@echo "make eval is not implemented yet (Phase 3)." && exit 1
