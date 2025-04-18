"""Fix: Add thickness to finished_product table

Revision ID: 87d430abf123
Revises: add_thickness_panel
Create Date: 2025-04-18 12:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '87d430abf123'
down_revision = 'add_thickness_panel'
branch_labels = None
depends_on = None


def upgrade():
    # Проверяем существование колонки thickness в таблице finished_products
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('finished_products')]
    
    # Добавляем колонку thickness, если она еще не существует
    if 'thickness' not in columns:
        op.add_column('finished_products', sa.Column('thickness', sa.Float(), nullable=False, server_default='0.5'))
        print("Колонка thickness успешно добавлена в таблицу finished_products")
    else:
        print("Колонка thickness уже существует в таблице finished_products")


def downgrade():
    # Удаление колонки thickness из таблицы finished_products
    op.drop_column('finished_products', 'thickness') 