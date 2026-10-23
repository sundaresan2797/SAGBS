"""remove transport tables and rename finance permissions to payroll

Vehicles, EMI, vendor payments and client payments move out of EMS into a
separate Transport & Logistics system later; EMS keeps payroll only. The
finance:view / finance:manage permissions become payroll:view / payroll:manage
(renamed in place so existing role assignments keep working).

Revision ID: c5a1a6b46fe4
Revises: 6bf4383e7f5f
Create Date: 2026-09-20 12:18:05.988210

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c5a1a6b46fe4'
down_revision: Union[str, None] = '6bf4383e7f5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Dependents first: these three all point at vehicles.
    op.drop_index('ix_vehicle_emis_vehicle_id', table_name='vehicle_emis')
    op.drop_table('vehicle_emis')
    op.drop_index('ix_client_payments_due_date', table_name='client_payments')
    op.drop_index('ix_client_payments_vehicle_id', table_name='client_payments')
    op.drop_table('client_payments')
    op.drop_index('ix_vendor_payments_due_date', table_name='vendor_payments')
    op.drop_index('ix_vendor_payments_vehicle_id', table_name='vendor_payments')
    op.drop_table('vendor_payments')
    op.drop_index('ix_vehicles_vehicle_number', table_name='vehicles')
    op.drop_table('vehicles')

    op.execute("DROP TYPE IF EXISTS vendor_payment_category")
    op.execute("DROP TYPE IF EXISTS vehicle_status")

    op.execute(
        "UPDATE permissions SET code = 'payroll:view', "
        "description = 'View salary records, payroll runs and expense claims' "
        "WHERE code = 'finance:view'"
    )
    op.execute(
        "UPDATE permissions SET code = 'payroll:manage', "
        "description = 'Set salaries, run payroll, mark salaries paid, and review expense claims' "
        "WHERE code = 'finance:manage'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE permissions SET code = 'finance:view', "
        "description = 'View vehicle finance, vendor/client payments, salary and expense records' "
        "WHERE code = 'payroll:view'"
    )
    op.execute(
        "UPDATE permissions SET code = 'finance:manage', "
        "description = 'Create and update vehicle finance, vendor/client payments, salary and expense records' "
        "WHERE code = 'payroll:manage'"
    )

    op.create_table('vehicles',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('vehicle_number', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
    sa.Column('vehicle_type', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    sa.Column('driver_employee_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('driver_name', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
    sa.Column('status', postgresql.ENUM('ACTIVE', 'INACTIVE', name='vehicle_status'), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['driver_employee_id'], ['employees.id'], name='vehicles_driver_employee_id_fkey', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name='vehicles_pkey')
    )
    op.create_index('ix_vehicles_vehicle_number', 'vehicles', ['vehicle_number'], unique=True)
    op.create_table('vendor_payments',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('vendor_name', sa.VARCHAR(length=150), autoincrement=False, nullable=False),
    sa.Column('category', postgresql.ENUM('FUEL', 'MAINTENANCE', 'INSURANCE', 'PERMIT_FITNESS', 'TOLL', 'REPAIR', 'OTHER', name='vendor_payment_category'), autoincrement=False, nullable=False),
    sa.Column('vehicle_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('amount', sa.NUMERIC(precision=12, scale=2), autoincrement=False, nullable=False),
    sa.Column('due_date', sa.DATE(), autoincrement=False, nullable=False),
    sa.Column('paid_date', sa.DATE(), autoincrement=False, nullable=True),
    sa.Column('description', sa.VARCHAR(length=500), autoincrement=False, nullable=True),
    sa.Column('created_by', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='vendor_payments_created_by_fkey', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], name='vendor_payments_vehicle_id_fkey', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name='vendor_payments_pkey')
    )
    op.create_index('ix_vendor_payments_vehicle_id', 'vendor_payments', ['vehicle_id'], unique=False)
    op.create_index('ix_vendor_payments_due_date', 'vendor_payments', ['due_date'], unique=False)
    op.create_table('client_payments',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('client_name', sa.VARCHAR(length=150), autoincrement=False, nullable=False),
    sa.Column('invoice_number', sa.VARCHAR(length=50), autoincrement=False, nullable=True),
    sa.Column('vehicle_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('amount', sa.NUMERIC(precision=12, scale=2), autoincrement=False, nullable=False),
    sa.Column('due_date', sa.DATE(), autoincrement=False, nullable=False),
    sa.Column('received_date', sa.DATE(), autoincrement=False, nullable=True),
    sa.Column('description', sa.VARCHAR(length=500), autoincrement=False, nullable=True),
    sa.Column('created_by', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='client_payments_created_by_fkey', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], name='client_payments_vehicle_id_fkey', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name='client_payments_pkey')
    )
    op.create_index('ix_client_payments_vehicle_id', 'client_payments', ['vehicle_id'], unique=False)
    op.create_index('ix_client_payments_due_date', 'client_payments', ['due_date'], unique=False)
    op.create_table('vehicle_emis',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('vehicle_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('monthly_amount', sa.NUMERIC(precision=12, scale=2), autoincrement=False, nullable=False),
    sa.Column('loan_amount', sa.NUMERIC(precision=12, scale=2), autoincrement=False, nullable=True),
    sa.Column('start_date', sa.DATE(), autoincrement=False, nullable=False),
    sa.Column('end_date', sa.DATE(), autoincrement=False, nullable=True),
    sa.Column('is_active', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], name='vehicle_emis_vehicle_id_fkey', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name='vehicle_emis_pkey')
    )
    op.create_index('ix_vehicle_emis_vehicle_id', 'vehicle_emis', ['vehicle_id'], unique=True)
