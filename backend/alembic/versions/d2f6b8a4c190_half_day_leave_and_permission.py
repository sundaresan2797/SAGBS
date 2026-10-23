"""half-day leave, leave recorded on someone's behalf, and short permissions

- leave_requests: which half of the day (day_part), and who entered it for the employee (recorded_by_*, recorded_late)
- short_permissions: a new table for "permission" (an approved absence of a few hours)
- salary_payments.half_leave_days: how many half-day leaves a payslip counted (old payslips stay NULL)

Only adds things: no existing row is changed, so it is safe to run on live data.

Revision ID: d2f6b8a4c190
Revises: c9e4a1d7f305
Create Date: 2026-09-28 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd2f6b8a4c190'
down_revision: Union[str, None] = 'c9e4a1d7f305'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('leave_requests', sa.Column('day_part', sa.String(length=12), nullable=True))
    op.add_column('leave_requests', sa.Column('recorded_by_user_id', sa.Integer(), nullable=True))
    op.add_column('leave_requests', sa.Column('recorded_by_name', sa.String(length=150), nullable=True))
    op.add_column('leave_requests', sa.Column('recorded_late', sa.Boolean(), server_default='false', nullable=False))
    op.create_foreign_key(
        'leave_requests_recorded_by_user_id_fkey', 'leave_requests', 'users', ['recorded_by_user_id'], ['id'], ondelete='SET NULL'
    )
    op.add_column('salary_payments', sa.Column('half_leave_days', sa.Integer(), nullable=True))
    op.create_table(
        'short_permissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('permission_date', sa.Date(), nullable=False),
        sa.Column('minutes', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=255), nullable=False),
        sa.Column('recorded_by_user_id', sa.Integer(), nullable=True),
        sa.Column('recorded_by_name', sa.String(length=150), nullable=False),
        sa.Column('recorded_late', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['recorded_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('employee_id', 'permission_date', name='uq_short_permission_employee_date'),
    )
    op.create_index('ix_short_permissions_employee_id', 'short_permissions', ['employee_id'])
    op.create_index('ix_short_permissions_permission_date', 'short_permissions', ['permission_date'])


def downgrade() -> None:
    op.drop_index('ix_short_permissions_permission_date', table_name='short_permissions')
    op.drop_index('ix_short_permissions_employee_id', table_name='short_permissions')
    op.drop_table('short_permissions')
    op.drop_column('salary_payments', 'half_leave_days')
    op.drop_constraint('leave_requests_recorded_by_user_id_fkey', 'leave_requests', type_='foreignkey')
    op.drop_column('leave_requests', 'recorded_late')
    op.drop_column('leave_requests', 'recorded_by_name')
    op.drop_column('leave_requests', 'recorded_by_user_id')
    op.drop_column('leave_requests', 'day_part')
