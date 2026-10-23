"""add user token_version for session invalidation

Revision ID: e6b13285688d
Revises: 0a016bb9e72c
Create Date: 2026-09-18 10:56:15.704040

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6b13285688d'
down_revision: Union[str, None] = '0a016bb9e72c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('token_version', sa.Integer(), nullable=False, server_default='1'))
    op.alter_column('users', 'token_version', server_default=None)


def downgrade() -> None:
    op.drop_column('users', 'token_version')
