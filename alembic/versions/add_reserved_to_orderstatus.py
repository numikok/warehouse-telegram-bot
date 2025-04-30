"""add_reserved_to_orderstatus

Revision ID: afc12345def6
Revises: merge_heroku_heads
Create Date: 2025-04-30 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'afc12345def6'
down_revision: Union[str, None] = 'merge_heroku_heads'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Execute PostgreSQL command to add the RESERVED value to the enum
    op.execute("ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'reserved'")
    
    # Ensure all tables using the enum know about the new value
    op.execute("COMMIT")


def downgrade() -> None:
    # Cannot easily remove enum values in PostgreSQL
    pass 