"""tell managers about leave requests that were already waiting

The "Leave request to review" notification is only created when someone applies from now on, so every
request already pending when it was introduced never told its approver anything. This gives each such
request one notification, addressed to the employee's direct manager, worded exactly like the live one.
Safe to re-run: a request that already has its notification (same person, same wording) is skipped.

Revision ID: c9e4a1d7f305
Revises: b7d1e5f3a692
Create Date: 2026-09-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c9e4a1d7f305'
down_revision: Union[str, None] = 'b7d1e5f3a692'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO notifications (user_id, title, message, notification_type, is_read, created_at, updated_at)
        SELECT m.user_id,
               'Leave request to review',
               e.first_name || ' ' || e.last_name || ' asked for leave from ' || l.start_date || ' to ' || l.end_date || '.',
               'LEAVE_REQUESTED',
               false,
               l.created_at,
               l.created_at
        FROM leave_requests l
        JOIN employees e ON e.id = l.employee_id
        JOIN employees m ON m.id = e.manager_id
        WHERE l.status = 'PENDING'
          AND m.user_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM notifications n
              WHERE n.user_id = m.user_id
                AND n.notification_type = 'LEAVE_REQUESTED'
                AND n.message = e.first_name || ' ' || e.last_name || ' asked for leave from ' || l.start_date || ' to ' || l.end_date || '.'
          )
        """
    )


def downgrade() -> None:
    # A data-only catch-up: the notifications are real messages the approvers may already have read,
    # so they are not deleted on downgrade.
    pass
