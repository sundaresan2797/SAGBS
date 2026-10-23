"""document types become a database table (managed by Admin/HR) instead of a fixed list

The six built-in kinds are copied into the new document_types table, every
existing document is re-pointed at its row (so nothing is lost or renamed),
then the fixed "document_type" enum column and Postgres enum type are dropped.
Adds the document_type:manage permission for ADMIN and HR.

Revision ID: c94d2f7a1b63
Revises: b81f6c2d9e47
Create Date: 2026-09-20 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c94d2f7a1b63'
down_revision: Union[str, None] = 'b81f6c2d9e47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BUILT_IN = [
    ("OFFER_LETTER", "Offer Letter"),
    ("EMPLOYMENT_CONTRACT", "Employment Contract"),
    ("ID_PROOF", "ID Proof"),
    ("RESUME", "Resume"),
    ("CERTIFICATION", "Certification"),
    ("OTHER", "Other"),
]
PERMISSION = ("document_type:manage", "Manage document types (the kinds of document employees can upload)")


def upgrade() -> None:
    op.create_table(
        'document_types',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=30), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('requires_expiry', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_document_types_code'), 'document_types', ['code'], unique=True)

    values = ", ".join(f"('{code}', '{name}', false, true, now(), now())" for code, name in BUILT_IN)
    op.execute(
        "INSERT INTO document_types (code, name, requires_expiry, is_active, created_at, updated_at) "
        f"VALUES {values}"
    )

    op.add_column('employee_documents', sa.Column('document_type_id', sa.Integer(), nullable=True))
    op.execute(
        "UPDATE employee_documents d SET document_type_id = t.id "
        "FROM document_types t WHERE t.code = d.document_type::text"
    )
    op.alter_column('employee_documents', 'document_type_id', nullable=False)
    op.create_foreign_key(
        'employee_documents_document_type_id_fkey', 'employee_documents', 'document_types',
        ['document_type_id'], ['id'], ondelete='RESTRICT',
    )
    op.create_index(op.f('ix_employee_documents_document_type_id'), 'employee_documents', ['document_type_id'])
    op.drop_column('employee_documents', 'document_type')
    op.execute("DROP TYPE IF EXISTS document_type")

    op.execute(
        "INSERT INTO permissions (code, description, created_at, updated_at) "
        f"SELECT '{PERMISSION[0]}', '{PERMISSION[1]}', now(), now() "
        f"WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = '{PERMISSION[0]}')"
    )
    op.execute(
        "INSERT INTO role_permissions (role_id, permission_id) "
        "SELECT r.id, p.id FROM roles r, permissions p "
        f"WHERE r.name IN ('ADMIN', 'HR') AND p.code = '{PERMISSION[0]}' "
        "AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id)"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id = (SELECT id FROM permissions WHERE code = "
        f"'{PERMISSION[0]}')"
    )
    op.execute(f"DELETE FROM permissions WHERE code = '{PERMISSION[0]}'")

    codes = ", ".join(f"'{code}'" for code, _ in BUILT_IN)
    op.execute(f"CREATE TYPE document_type AS ENUM ({codes})")
    op.add_column(
        'employee_documents',
        sa.Column('document_type', postgresql.ENUM(name='document_type', create_type=False), nullable=True),
    )
    # A type added later (not one of the six) has no place in the old fixed list: it falls back to OTHER.
    op.execute(
        "UPDATE employee_documents d SET document_type = "
        f"(CASE WHEN t.code IN ({codes}) THEN t.code ELSE 'OTHER' END)::document_type "
        "FROM document_types t WHERE t.id = d.document_type_id"
    )
    op.alter_column('employee_documents', 'document_type', nullable=False)
    op.drop_index(op.f('ix_employee_documents_document_type_id'), table_name='employee_documents')
    op.drop_constraint('employee_documents_document_type_id_fkey', 'employee_documents', type_='foreignkey')
    op.drop_column('employee_documents', 'document_type_id')

    op.drop_index(op.f('ix_document_types_code'), table_name='document_types')
    op.drop_table('document_types')
