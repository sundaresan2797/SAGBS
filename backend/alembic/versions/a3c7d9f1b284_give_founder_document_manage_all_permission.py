"""give Founder the document:manage_all permission

Founder ("Top Head") could see the company-wide dashboard, attendance and leave data, but had
no way to view documents employees upload (ID proofs, certificates, etc.) - document:manage_all
was only granted to ADMIN (automatically, non-payroll) and HR. list_documents/get_document_for_download
already resolve authorization generically via _resolve_target_employee, which checks this exact
permission code regardless of role, so granting it to Founder needs no service-layer change - only
the frontend needed a place to call it from (see the new Documents section on EmployeeDetailPage).

Revision ID: a3c7d9f1b284
Revises: f1a4b8e2c657
Create Date: 2026-09-23 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a3c7d9f1b284'
down_revision: Union[str, None] = 'f1a4b8e2c657'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'FOUNDER' AND p.code = 'document:manage_all'
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE role_id = (SELECT id FROM roles WHERE name = 'FOUNDER')
          AND permission_id = (SELECT id FROM permissions WHERE code = 'document:manage_all')
        """
    )
