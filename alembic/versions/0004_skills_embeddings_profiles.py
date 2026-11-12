"""Phase 2: role family, posting skills, posting embeddings, user profiles and profile embeddings

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("postings", sa.Column("role_family", sa.String(length=24), nullable=True))
    op.create_table(
        "posting_skills",
        sa.Column("posting_id", sa.Integer(), nullable=False),
        sa.Column("skill", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["posting_id"], ["postings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("posting_id", "skill"),
    )
    op.create_index("ix_posting_skills_skill", "posting_skills", ["skill"])
    # No ANN index on purpose: ~10k x 384 floats is scanned exactly in milliseconds (ADR 0012).
    op.create_table(
        "posting_embeddings",
        sa.Column("posting_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["posting_id"], ["postings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("posting_id"),
    )
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("target_roles", sa.JSON(), nullable=False),
        sa.Column("target_locations", sa.JSON(), nullable=False),
        sa.Column("remote_ok", sa.Boolean(), nullable=False),
        sa.Column("grad_date", sa.Date(), nullable=True),
        sa.Column("needs_sponsorship", sa.Boolean(), nullable=False),
        sa.Column("about_text", sa.Text(), nullable=True),
        sa.Column("profile_document", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "profile_embeddings",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("profile_embeddings")
    op.drop_table("user_profiles")
    op.drop_table("posting_embeddings")
    op.drop_index("ix_posting_skills_skill", table_name="posting_skills")
    op.drop_table("posting_skills")
    op.drop_column("postings", "role_family")
