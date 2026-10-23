"""give HR the task:read_own permission

HR staff are employees too and can be assigned tasks, but the HR role had no
task permissions at all, so they had no "My Tasks" view.

Revision ID: a7d3e91b4c20
Revises: c5a1a6b46fe4
Create Date: 2026-09-20 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7d3e91b4c20'
down_revision: Union[str, None] = 'c5a1a6b46fe4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'HR' AND p.code = 'task:read_own'
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE role_id = (SELECT id FROM roles WHERE name = 'HR')
          AND permission_id = (SELECT id FROM permissions WHERE code = 'task:read_own')
        """
    )
