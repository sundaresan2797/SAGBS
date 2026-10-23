"""add leave type accrual frequency

Revision ID: 0a016bb9e72c
Revises: 4ca981e09ad5
Create Date: 2026-09-17 18:52:07.148175

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0a016bb9e72c'
down_revision: Union[str, None] = '4ca981e09ad5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    accrual_frequency = sa.Enum('ANNUAL', 'MONTHLY', name='leave_accrual_frequency')
    accrual_frequency.create(op.get_bind(), checkfirst=True)
    # Existing leave types (Casual/Sick/Earned/Unpaid) all keep today's
    # behavior - a full annual grant - unless HR later switches one to
    # monthly accrual via the leave type management UI.
    op.add_column(
        'leave_types',
        sa.Column('accrual_frequency', accrual_frequency, nullable=False, server_default='ANNUAL'),
    )
    op.alter_column('leave_types', 'accrual_frequency', server_default=None)


def downgrade() -> None:
    op.drop_column('leave_types', 'accrual_frequency')
    sa.Enum(name='leave_accrual_frequency').drop(op.get_bind(), checkfirst=True)
