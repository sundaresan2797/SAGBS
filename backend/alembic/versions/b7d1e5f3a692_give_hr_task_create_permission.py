"""give HR the task:create permission

Some real HR employees genuinely manage people (the manager_id chain), not just oversee the
company - HR Head/HR staff can have their own direct reports (confirmed live: J Lokesh, Ritu
Kapoor and Hannah Reyes each manage real people in production). HR previously had task:read_team
(company-wide visibility, via report:view widening) but not task:create, so those managers could
see their team's tasks but had no "Assign a task" control anywhere - create_task's manager_id
check already restricts task assignment to real direct reports regardless of role, exactly like
leave:approve_team does for leave, so this is safe for every HR login, not just the ones who
happen to manage people.

Revision ID: b7d1e5f3a692
Revises: a3c7d9f1b284
Create Date: 2026-09-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7d1e5f3a692'
down_revision: Union[str, None] = 'a3c7d9f1b284'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'HR' AND p.code = 'task:create'
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
          AND permission_id = (SELECT id FROM permissions WHERE code = 'task:create')
        """
    )
