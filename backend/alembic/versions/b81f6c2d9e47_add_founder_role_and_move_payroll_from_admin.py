"""add FOUNDER role and move payroll access from ADMIN to FOUNDER

The business owner gets their own role (oversight plus the final say on
money), and ADMIN becomes a pure system-administration role with no access
to salary data. The permission lists are written out here on purpose, so this
migration keeps meaning the same thing even if the app's defaults change later.

Revision ID: b81f6c2d9e47
Revises: a7d3e91b4c20
Create Date: 2026-09-20 17:05:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b81f6c2d9e47'
down_revision: Union[str, None] = 'a7d3e91b4c20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FOUNDER_PERMISSIONS = [
    "employee:read",
    "attendance:read_own",
    "attendance:read_team",
    "attendance:read_all",
    "attendance:mark",
    "leave:apply",
    "leave:approve_team",
    "leave:manage_all",
    "task:create",
    "task:read_own",
    "task:read_team",
    "document:manage_own",
    "notification:read",
    "report:view",
    "audit:view",
    "expense:submit",
    "payroll:view",
    "payroll:manage",
]
PAYROLL_PERMISSIONS = ["payroll:view", "payroll:manage"]


def _quoted(codes: list[str]) -> str:
    return ", ".join(f"'{c}'" for c in codes)


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO roles (name, description, created_at, updated_at)
        SELECT 'FOUNDER', 'Business owner: company-wide oversight and final say on payroll', now(), now()
        WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'FOUNDER')
        """
    )
    op.execute(
        f"""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'FOUNDER' AND p.code IN ({_quoted(FOUNDER_PERMISSIONS)})
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
        """
    )
    op.execute(
        f"""
        DELETE FROM role_permissions
        WHERE role_id = (SELECT id FROM roles WHERE name = 'ADMIN')
          AND permission_id IN (SELECT id FROM permissions WHERE code IN ({_quoted(PAYROLL_PERMISSIONS)}))
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'ADMIN' AND p.code IN ({_quoted(PAYROLL_PERMISSIONS)})
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
        """
    )
    op.execute(
        "DELETE FROM role_permissions WHERE role_id = (SELECT id FROM roles WHERE name = 'FOUNDER')"
    )
    # Fails (by design) if any user still holds the FOUNDER role.
    op.execute("DELETE FROM roles WHERE name = 'FOUNDER'")
