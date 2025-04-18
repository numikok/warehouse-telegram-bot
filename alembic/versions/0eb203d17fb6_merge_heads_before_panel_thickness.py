"""merge_heads_before_panel_thickness

Revision ID: 0eb203d17fb6
Revises: d7f45a6b789c, merge_heads
Create Date: 2025-04-18 20:07:35.155128

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0eb203d17fb6'
down_revision: Union[str, None] = ('d7f45a6b789c', 'merge_heads')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass 