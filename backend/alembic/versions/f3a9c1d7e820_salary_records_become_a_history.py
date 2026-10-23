"""salary_records becomes a history (one row per change) instead of one row per employee

Drops the unique index on employee_id and replaces it with a plain (non-unique) one, and adds an
index on effective_from - "current" salary is now worked out by the repository (latest
effective_from that has arrived), not by there being only one row. No data is changed by this
migration; existing rows become the first entry in each employee's history. A best-effort
backfill of pre-raise salaries lives in app/backfill_salary_history.py, run separately.

Revision ID: f3a9c1d7e820
Revises: e4b7c2a9d135
Create Date: 2026-09-22 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f3a9c1d7e820'
down_revision: Union[str, None] = 'e4b7c2a9d135'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index('ix_salary_records_employee_id', table_name='salary_records')
    op.create_index('ix_salary_records_employee_id', 'salary_records', ['employee_id'], unique=False)
    op.create_index('ix_salary_records_effective_from', 'salary_records', ['effective_from'], unique=False)


def downgrade() -> None:
    # Only safe if every employee still has at most one row - a downgrade after real history has
    # built up would violate the old unique constraint and must be resolved by hand first.
    op.drop_index('ix_salary_records_effective_from', table_name='salary_records')
    op.drop_index('ix_salary_records_employee_id', table_name='salary_records')
    op.create_index('ix_salary_records_employee_id', 'salary_records', ['employee_id'], unique=True)
