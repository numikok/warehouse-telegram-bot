"""Remove deprecated fields from the orders table

Revision ID: remove_deprecated_order_fields
Revises: update_order_structure
Create Date: 2025-05-08 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'remove_deprecated_order_fields'
down_revision: Union[str, None] = 'update_order_structure'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Remove deprecated columns from orders table that are now stored in other tables
    op.drop_column('orders', 'film_code')
    op.drop_column('orders', 'panel_quantity')
    op.drop_column('orders', 'joint_type')
    op.drop_column('orders', 'joint_color')
    op.drop_column('orders', 'joint_quantity')
    op.drop_column('orders', 'glue_quantity')
    op.drop_column('orders', 'panel_thickness')
    
    # Also update completed_orders table to match
    op.drop_column('completed_orders', 'film_code')
    op.drop_column('completed_orders', 'panel_quantity')
    op.drop_column('completed_orders', 'joint_type')
    op.drop_column('completed_orders', 'joint_color')
    op.drop_column('completed_orders', 'joint_quantity')
    op.drop_column('completed_orders', 'glue_quantity')
    op.drop_column('completed_orders', 'panel_thickness')

def downgrade() -> None:
    # Add back all the columns with nullable=True to ensure backward compatibility
    op.add_column('orders', sa.Column('film_code', sa.String(), nullable=True))
    op.add_column('orders', sa.Column('panel_quantity', sa.Integer(), nullable=True))
    op.add_column('orders', sa.Column('joint_type', sa.Enum('BUTTERFLY', 'SIMPLE', 'CLOSING', name='jointtype'), nullable=True))
    op.add_column('orders', sa.Column('joint_color', sa.String(), nullable=True))
    op.add_column('orders', sa.Column('joint_quantity', sa.Integer(), nullable=True))
    op.add_column('orders', sa.Column('glue_quantity', sa.Integer(), nullable=True))
    op.add_column('orders', sa.Column('panel_thickness', sa.Float(), nullable=True, server_default='0.5'))
    
    # Restore completed_orders columns too
    op.add_column('completed_orders', sa.Column('film_code', sa.String(), nullable=True))
    op.add_column('completed_orders', sa.Column('panel_quantity', sa.Integer(), nullable=True))
    op.add_column('completed_orders', sa.Column('joint_type', sa.Enum('BUTTERFLY', 'SIMPLE', 'CLOSING', name='jointtype'), nullable=True))
    op.add_column('completed_orders', sa.Column('joint_color', sa.String(), nullable=True))
    op.add_column('completed_orders', sa.Column('joint_quantity', sa.Integer(), nullable=True))
    op.add_column('completed_orders', sa.Column('glue_quantity', sa.Integer(), nullable=True))
    op.add_column('completed_orders', sa.Column('panel_thickness', sa.Float(), nullable=True, server_default='0.5')) 