"""Create metrics table

Revision ID: 001
Revises: None
Create Date: 2026-04-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("metric_name", sa.String(length=255), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("extra_data", sa.Text(), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("metric_date", "metric_name", name="uq_metrics_date_name"),
    )

    op.create_index("idx_metrics_date", "metrics", ["metric_date"])
    op.create_index("idx_metrics_name", "metrics", ["metric_name"])


def downgrade() -> None:
    op.drop_index("idx_metrics_name")
    op.drop_index("idx_metrics_date")
    op.drop_table("metrics")
