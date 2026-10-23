"""give Executive the payroll:view permission

Company leadership (Founder/CEO/COO/CTO/CFO logins using the EXECUTIVE role) should be able to see
Salary Records and the Attendance Summary (both gated by payroll:view) the same way Founder can, but
should not be able to set a salary, run payroll, mark a payment, or approve/pay an expense claim -
those stay payroll:manage, limited to Founder and Accountant. This only grants the read-only half.

Revision ID: a5e3602b0ff8
Revises: d2f6b8a4c190
Create Date: 2026-10-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a5e3602b0ff8'
down_revision: Union[str, None] = 'd2f6b8a4c190'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'EXECUTIVE' AND p.code = 'payroll:view'
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE role_id = (SELECT id FROM roles WHERE name = 'EXECUTIVE')
          AND permission_id = (SELECT id FROM permissions WHERE code = 'payroll:view')
        """
    )
