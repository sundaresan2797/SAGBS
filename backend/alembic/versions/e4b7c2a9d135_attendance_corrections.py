"""attendance corrections: who fixed a missed check-out, when and why

Adds four nullable columns to attendance; nothing existing is rewritten.
No new permission: the service decides who may fix a record from existing
access (attendance:read_all = whole company, otherwise direct reports only,
and never your own record).

Revision ID: e4b7c2a9d135
Revises: c94d2f7a1b63
Create Date: 2026-09-21 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e4b7c2a9d135'
down_revision: Union[str, None] = 'c94d2f7a1b63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('attendance', sa.Column('corrected_by_user_id', sa.Integer(), nullable=True))
    op.add_column('attendance', sa.Column('corrected_by_name', sa.String(length=150), nullable=True))
    op.add_column('attendance', sa.Column('corrected_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('attendance', sa.Column('correction_reason', sa.String(length=255), nullable=True))
    op.create_foreign_key(
        'attendance_corrected_by_user_id_fkey', 'attendance', 'users',
        ['corrected_by_user_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('attendance_corrected_by_user_id_fkey', 'attendance', type_='foreignkey')
    op.drop_column('attendance', 'correction_reason')
    op.drop_column('attendance', 'corrected_at')
    op.drop_column('attendance', 'corrected_by_name')
    op.drop_column('attendance', 'corrected_by_user_id')
