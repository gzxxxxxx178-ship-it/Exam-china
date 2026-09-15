"""add source identifiers for ingestion

Revision ID: bd82b7713e01
Revises: 77a9ec56a588
Create Date: 2026-09-15 10:31:30.040677
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'bd82b7713e01'
down_revision: Union[str, Sequence[str], None] = '77a9ec56a588'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "exam_event", sa.Column("source_event_id", sa.String(length=180), nullable=True)
    )
    op.execute("UPDATE exam_event SET source_event_id = 'legacy-event-' || id")
    with op.batch_alter_table("exam_event") as batch_op:
        batch_op.alter_column("source_event_id", existing_type=sa.String(180), nullable=False)
        batch_op.create_unique_constraint(
            "uq_event_batch_source_id", ["batch_id", "source_event_id"]
        )

    with op.batch_alter_table("raw_document") as batch_op:
        batch_op.create_unique_constraint(
            "uq_raw_source_url_hash", ["source_id", "canonical_url", "content_hash"]
        )

    op.add_column(
        "recruitment_batch",
        sa.Column("source_batch_id", sa.String(length=180), nullable=True),
    )
    op.execute("UPDATE recruitment_batch SET source_batch_id = 'legacy-batch-' || id")
    with op.batch_alter_table("recruitment_batch") as batch_op:
        batch_op.alter_column("source_batch_id", existing_type=sa.String(180), nullable=False)
        batch_op.create_unique_constraint(
            "uq_batch_source_external_id", ["source_id", "source_batch_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("recruitment_batch") as batch_op:
        batch_op.drop_constraint("uq_batch_source_external_id", type_="unique")
        batch_op.drop_column("source_batch_id")
    with op.batch_alter_table("raw_document") as batch_op:
        batch_op.drop_constraint("uq_raw_source_url_hash", type_="unique")
    with op.batch_alter_table("exam_event") as batch_op:
        batch_op.drop_constraint("uq_event_batch_source_id", type_="unique")
        batch_op.drop_column("source_event_id")
