"""give HR the task:read_team permission (for the new company-wide task view)

HR needs to reach the /tasks/team endpoint at all before report:view can widen
it to every task in the company. HR has no direct reports of its own, so
task:read_team here is purely the gate to that company-wide view, not a grant
of team-scoped visibility (HR already had report:view).

Revision ID: d6e2f8a4c913
Revises: a1c4e8f2b7d3
Create Date: 2026-09-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd6e2f8a4c913'
down_revision: Union[str, None] = 'a1c4e8f2b7d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'HR' AND p.code = 'task:read_team'
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
          AND permission_id = (SELECT id FROM permissions WHERE code = 'task:read_team')
        """
    )
