"""give HR the leave:approve_team permission

Some real HR employees genuinely are someone's manager (manager_id chain), not just company-wide
overseers - HR previously had leave:manage_all (read-only visibility into every request) but not
leave:approve_team, so the "Approve Leave" screen's actionable section never rendered for HR at
all, even for their own direct reports. get_team_leave_requests already scopes strictly by the
manager_id chain regardless of role and returns an empty list for anyone with no reports, so this
is safe for every HR login, not just the ones who happen to manage people.

Revision ID: f1a4b8e2c657
Revises: d6e2f8a4c913
Create Date: 2026-09-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f1a4b8e2c657'
down_revision: Union[str, None] = 'd6e2f8a4c913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'HR' AND p.code = 'leave:approve_team'
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
          AND permission_id = (SELECT id FROM permissions WHERE code = 'leave:approve_team')
        """
    )
