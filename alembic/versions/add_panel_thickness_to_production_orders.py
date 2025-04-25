"""Add panel_thickness to production_orders

Revision ID: add_panel_thickness_to_production_orders
Revises: e50b65a6b669
Create Date: 2025-04-18 15:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_panel_thickness_to_production_orders'
down_revision = 'e50b65a6b669'
branch_labels = None
depends_on = None


def upgrade():
    # Проверяем существование колонки panel_thickness в таблице production_orders
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('production_orders')]
    
    # Добавляем колонку panel_thickness, если она еще не существует
    if 'panel_thickness' not in columns:
        op.add_column('production_orders', sa.Column('panel_thickness', sa.Float(), nullable=False, server_default='0.5'))
        print("Колонка panel_thickness успешно добавлена в таблицу production_orders")
    else:
        print("Колонка panel_thickness уже существует в таблице production_orders")


def downgrade():
    # Удаление колонки panel_thickness из таблицы production_orders
    op.drop_column('production_orders', 'panel_thickness') 