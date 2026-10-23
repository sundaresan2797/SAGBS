"""salary_payments gains an attendance-breakdown snapshot (for Step 3: payroll now pays by attendance)

Nine nullable columns, additive only - no existing row is touched. Payments made before this
(when everyone was paid their full salary regardless of attendance) simply have none of these;
only NEW payroll runs, from now on, fill them in.

Revision ID: a1c4e8f2b7d3
Revises: f3a9c1d7e820
Create Date: 2026-09-22 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1c4e8f2b7d3'
down_revision: Union[str, None] = 'f3a9c1d7e820'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INT_COLUMNS = [
    'total_days', 'present_days', 'late_days', 'half_days',
    'paid_leave_days', 'unpaid_leave_days', 'absent_days', 'days_off_days',
]


def upgrade() -> None:
    for name in INT_COLUMNS:
        op.add_column('salary_payments', sa.Column(name, sa.Integer(), nullable=True))
    op.add_column('salary_payments', sa.Column('payable_days', sa.Numeric(5, 1), nullable=True))
    op.add_column('salary_payments', sa.Column('cut_days', sa.Numeric(5, 1), nullable=True))


def downgrade() -> None:
    op.drop_column('salary_payments', 'cut_days')
    op.drop_column('salary_payments', 'payable_days')
    for name in reversed(INT_COLUMNS):
        op.drop_column('salary_payments', name)
