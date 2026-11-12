"""count reopened postings separately from edits in ingestion_runs

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Historic runs never reopened anything (a first reopen has not happened yet), so 0 is correct for them.
    op.add_column(
        "ingestion_runs",
        sa.Column("reopened", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("ingestion_runs", "reopened")
