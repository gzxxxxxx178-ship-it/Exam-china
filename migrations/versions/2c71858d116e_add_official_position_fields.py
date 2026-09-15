"""add official position fields

Revision ID: 2c71858d116e
Revises: bd82b7713e01
Create Date: 2026-09-15 14:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2c71858d116e"
down_revision: Union[str, Sequence[str], None] = "bd82b7713e01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


POSITION_COLUMNS = (
    ("employer_name", sa.String(length=300)),
    ("institution_nature", sa.String(length=120)),
    ("position_attribute", sa.String(length=120)),
    ("position_distribution", sa.String(length=120)),
    ("description", sa.Text()),
    ("institution_level", sa.String(length=80)),
    ("exam_category", sa.String(length=160)),
    ("service_project_experience", sa.String(length=200)),
    ("professional_test_required", sa.String(length=40)),
    ("interview_ratio", sa.String(length=40)),
    ("settlement_location", sa.String(length=300)),
    ("department_website", sa.Text()),
    ("contact_phone", sa.String(length=300)),
)


def upgrade() -> None:
    with op.batch_alter_table("position") as batch_op:
        for name, column_type in POSITION_COLUMNS:
            batch_op.add_column(sa.Column(name, column_type, nullable=True))
        batch_op.create_index("ix_position_employer_name", ["employer_name"])
    with op.batch_alter_table("position_location") as batch_op:
        batch_op.add_column(sa.Column("province_name", sa.String(length=100)))
        batch_op.add_column(sa.Column("city_name", sa.String(length=100)))
        batch_op.create_index("ix_position_location_province_name", ["province_name"])
        batch_op.create_index("ix_position_location_city_name", ["city_name"])


def downgrade() -> None:
    with op.batch_alter_table("position_location") as batch_op:
        batch_op.drop_index("ix_position_location_city_name")
        batch_op.drop_index("ix_position_location_province_name")
        batch_op.drop_column("city_name")
        batch_op.drop_column("province_name")
    with op.batch_alter_table("position") as batch_op:
        batch_op.drop_index("ix_position_employer_name")
        for name, _ in reversed(POSITION_COLUMNS):
            batch_op.drop_column(name)
