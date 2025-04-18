"""Add thickness to finished_product table

Revision ID: d7f45a6b789c
Revises: e50b65a6b669
Create Date: 2023-05-01 12:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd7f45a6b789c'
down_revision = 'e50b65a6b669'
branch_labels = None
depends_on = None


def upgrade():
    # Добавление колонки thickness в таблицу finished_products
    op.add_column('finished_products', sa.Column('thickness', sa.Float(), nullable=False, server_default='0.5'))


def downgrade():
    # Удаление колонки thickness из таблицы finished_products
    op.drop_column('finished_products', 'thickness') 