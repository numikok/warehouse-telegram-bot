"""merge heads

Revision ID: merge_heads
Revises: 87d430abf123, add_panel_thickness_to_production_orders
Create Date: 2025-04-18 15:30:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'merge_heads'
down_revision = ('87d430abf123', 'add_panel_thickness_to_production_orders')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass 