"""entry-level and sponsorship evidence; sponsorship values restricted/offered/unclear

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("postings", sa.Column("entry_evidence", sa.String(length=16), nullable=True))
    op.add_column(
        "postings", sa.Column("entry_evidence_text", sa.String(length=300), nullable=True)
    )
    op.add_column("postings", sa.Column("sponsorship_evidence", sa.Text(), nullable=True))
    # Old value names -> new. Derived fields are refreshed properly by `make reparse`; this keeps the
    # column valid for any row until then.
    op.execute("UPDATE postings SET sponsorship = 'offered' WHERE sponsorship = 'sponsors'")
    op.execute("UPDATE postings SET sponsorship = 'unclear' WHERE sponsorship = 'unknown'")


def downgrade() -> None:
    op.execute("UPDATE postings SET sponsorship = 'sponsors' WHERE sponsorship = 'offered'")
    op.execute("UPDATE postings SET sponsorship = 'unknown' WHERE sponsorship = 'unclear'")
    op.drop_column("postings", "sponsorship_evidence")
    op.drop_column("postings", "entry_evidence_text")
    op.drop_column("postings", "entry_evidence")
