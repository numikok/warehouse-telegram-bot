"""Remove_film_thickness_add_panel_thickness

Revision ID: e50b65a6b669
Revises: 3bd7046278f0
Create Date: 2025-04-18 14:01:15.865324

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e50b65a6b669'
down_revision: Union[str, None] = '3bd7046278f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add panel_thickness column to Panel model and rename film_thickness to panel_thickness in other tables
    
    # First add panel_thickness column to panels (nullable first)
    op.add_column('panels', sa.Column('thickness', sa.Float(), nullable=True))
    
    # Set a default value for panel thickness
    op.execute("UPDATE panels SET thickness = 0.5")
    
    # Make the column NOT NULL
    op.alter_column('panels', 'thickness', nullable=False)
    
    # Add panel_thickness to orders and completed_orders (nullable first)
    op.add_column('orders', sa.Column('panel_thickness', sa.Float(), nullable=True))
    op.add_column('completed_orders', sa.Column('panel_thickness', sa.Float(), nullable=True))
    
    # Copy data from film_thickness to panel_thickness
    op.execute("UPDATE orders SET panel_thickness = film_thickness")
    op.execute("UPDATE completed_orders SET panel_thickness = film_thickness")
    
    # Make the columns NOT NULL
    op.alter_column('orders', 'panel_thickness', nullable=False)
    op.alter_column('completed_orders', 'panel_thickness', nullable=False)
    
    # Drop film_thickness columns
    op.drop_column('orders', 'film_thickness')
    op.drop_column('completed_orders', 'film_thickness')
    op.drop_column('production_orders', 'film_thickness')
    op.drop_column('films', 'thickness')


def downgrade() -> None:
    # Restore film_thickness columns and remove panel_thickness
    
    # Add film_thickness columns (nullable first)
    op.add_column('films', sa.Column('thickness', sa.Float(), nullable=True))
    op.add_column('production_orders', sa.Column('film_thickness', sa.Float(), nullable=True))
    op.add_column('orders', sa.Column('film_thickness', sa.Float(), nullable=True))
    op.add_column('completed_orders', sa.Column('film_thickness', sa.Float(), nullable=True))
    
    # Set default values
    op.execute("UPDATE films SET thickness = 0.5")
    op.execute("UPDATE production_orders SET film_thickness = 0.5")
    op.execute("UPDATE orders SET film_thickness = panel_thickness")
    op.execute("UPDATE completed_orders SET film_thickness = panel_thickness")
    
    # Make columns NOT NULL
    op.alter_column('films', 'thickness', nullable=False)
    op.alter_column('production_orders', 'film_thickness', nullable=False)
    op.alter_column('orders', 'film_thickness', nullable=False)
    op.alter_column('completed_orders', 'film_thickness', nullable=False)
    
    # Drop panel_thickness columns
    op.drop_column('orders', 'panel_thickness')
    op.drop_column('completed_orders', 'panel_thickness')
    op.drop_column('panels', 'thickness') 