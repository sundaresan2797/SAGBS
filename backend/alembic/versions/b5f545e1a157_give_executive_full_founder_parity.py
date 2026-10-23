"""give Executive full Founder parity

Executive is now meant for company leadership that should carry exactly the same powers as Founder (a
second owner/co-founder), not just a scoped business-leadership role. This adds the five permissions
Executive was still missing to match Founder exactly: attendance:read_all (company-wide attendance, not
just their own team), leave:manage_all (see/act on every leave request, not just their own reports),
document:manage_all, audit:view, and payroll:manage (set salaries, run payroll, mark paid, approve/pay
expense claims - on top of the payroll:view granted in a5e3602b0ff8). Executive still has none of the
system-config permissions (department/designation/leave_type/holiday management, user:manage, role:manage)
- those stay HR/ADMIN-only.

Revision ID: b5f545e1a157
Revises: a5e3602b0ff8
Create Date: 2026-10-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b5f545e1a157'
down_revision: Union[str, None] = 'a5e3602b0ff8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERMISSION_CODES = (
    "attendance:read_all",
    "leave:manage_all",
    "document:manage_all",
    "audit:view",
    "payroll:manage",
)


def upgrade() -> None:
    for code in PERMISSION_CODES:
        op.execute(
            f"""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id FROM roles r, permissions p
            WHERE r.name = 'EXECUTIVE' AND p.code = '{code}'
              AND NOT EXISTS (
                  SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
            """
        )


def downgrade() -> None:
    for code in PERMISSION_CODES:
        op.execute(
            f"""
            DELETE FROM role_permissions
            WHERE role_id = (SELECT id FROM roles WHERE name = 'EXECUTIVE')
              AND permission_id = (SELECT id FROM permissions WHERE code = '{code}')
            """
        )
