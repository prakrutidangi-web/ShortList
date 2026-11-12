"""initial schema: users, companies, postings, ingestion_runs

Revision ID: 0001
Revises:
Create Date: 2026-11-12 11:15:47.112044
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pgvector is needed from Phase 2 (embeddings); enabling it here keeps a fresh DB self-contained.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("ats", sa.String(length=32), nullable=False),
        sa.Column("board_token", sa.String(length=200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ats", "board_token"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_group", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("fetched", sa.Integer(), nullable=False),
        sa.Column("new", sa.Integer(), nullable=False),
        sa.Column("updated", sa.Integer(), nullable=False),
        sa.Column("closed", sa.Integer(), nullable=False),
        sa.Column("failed", sa.Integer(), nullable=False),
        sa.Column("skipped_by_guard", sa.Integer(), nullable=False),
        sa.Column("raw_path", sa.String(length=500), nullable=True),
        sa.Column("raw_sha256", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ingestion_runs_run_group"), "ingestion_runs", ["run_group"], unique=False
    )
    op.create_table(
        "postings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("apply_url", sa.String(length=1000), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description_text", sa.Text(), nullable=False),
        sa.Column("location_raw", sa.String(length=500), nullable=True),
        sa.Column("city", sa.String(length=200), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("is_remote", sa.Boolean(), nullable=True),
        sa.Column("years_min", sa.Integer(), nullable=True),
        sa.Column("seniority", sa.String(length=16), nullable=False),
        sa.Column("is_entry_level", sa.Boolean(), nullable=False),
        sa.Column("sponsorship", sa.String(length=16), nullable=False),
        sa.Column("source_posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("dedup_key", sa.String(length=64), nullable=False),
        sa.Column("canonical_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["canonical_id"],
            ["postings.id"],
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "source", "external_id"),
    )
    op.create_index(op.f("ix_postings_canonical_id"), "postings", ["canonical_id"], unique=False)
    op.create_index(
        "ix_postings_company_closed", "postings", ["company_id", "closed_at"], unique=False
    )
    op.create_index("ix_postings_dedup", "postings", ["company_id", "dedup_key"], unique=False)
    # The single local user (ADR 0006); every user-owned table will key on users.id.
    op.execute("INSERT INTO users (id, created_at) VALUES (1, now())")


def downgrade() -> None:
    op.drop_index("ix_postings_dedup", table_name="postings")
    op.drop_index("ix_postings_company_closed", table_name="postings")
    op.drop_index(op.f("ix_postings_canonical_id"), table_name="postings")
    op.drop_table("postings")
    op.drop_index(op.f("ix_ingestion_runs_run_group"), table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_table("users")
    op.drop_table("companies")
