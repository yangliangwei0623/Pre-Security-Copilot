"""Versioned JSON records for sessions, reports and immutable rule releases."""
from alembic import op
import sqlalchemy as sa
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("records", sa.Column("kind", sa.String(32), primary_key=True),
                    sa.Column("id", sa.String(100), primary_key=True),
                    sa.Column("body", sa.Text, nullable=False))


def downgrade():
    op.drop_table("records")
