"""Added is_active to users

Revision ID: a89bfa63f646
Revises: 959125f3f180
Create Date: 2026-01-11 08:12:56.540723

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a89bfa63f646'
down_revision: Union[str, None] = '959125f3f180'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_active column
    op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=True))
    
    # Set all existing users to active
    op.execute("UPDATE users SET is_active = TRUE WHERE is_active IS NULL")
    
    # Make column non-nullable
    op.alter_column('users', 'is_active', nullable=False)


def downgrade() -> None:
    p.drop_column('users', 'is_active')

