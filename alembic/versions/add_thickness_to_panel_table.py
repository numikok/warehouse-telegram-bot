"""add thickness to panel table

Revision ID: add_thickness_panel
Revises: e50b65a6b669
Create Date: 2023-04-16 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = 'add_thickness_panel'
down_revision = 'e50b65a6b669'
branch_labels = None
depends_on = None


def upgrade():
    # Check if thickness column already exists in panels table
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    existing_columns = [col['name'] for col in inspector.get_columns('panels')]
    
    # Add thickness column to panels table if it doesn't exist
    if 'thickness' not in existing_columns:
        op.add_column('panels', sa.Column('thickness', sa.Float(), nullable=True, server_default='0.5'))
        
        # Copy data from panel_thickness to thickness if panel_thickness exists
        if 'panel_thickness' in existing_columns:
            conn.execute(text('UPDATE panels SET thickness = panel_thickness'))
    
    # Check if thickness column exists in films table
    films_columns = [col['name'] for col in inspector.get_columns('films')]
    if 'thickness' in films_columns:
        op.drop_column('films', 'thickness')


def downgrade():
    # Add thickness back to films table if it doesn't exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'thickness' not in [col['name'] for col in inspector.get_columns('films')]:
        op.add_column('films', sa.Column('thickness', sa.Float(), nullable=True, server_default='0.5'))
    
    # Drop thickness from panels table if it exists
    if 'thickness' in [col['name'] for col in inspector.get_columns('panels')]:
        op.drop_column('panels', 'thickness') 