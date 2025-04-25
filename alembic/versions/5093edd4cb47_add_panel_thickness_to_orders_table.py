"""add_panel_thickness_to_orders_table

Revision ID: 5093edd4cb47
Revises: add_panel_thickness_to_production_orders
Create Date: 2025-04-18 20:08:09.953959

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5093edd4cb47'
down_revision: Union[str, None] = 'add_panel_thickness_to_production_orders'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем столбец panel_thickness в таблицу orders с дефолтным значением 0.5
    op.add_column('orders', sa.Column('panel_thickness', sa.Float(), nullable=False, server_default='0.5'))
    

def downgrade() -> None:
    # Удаляем столбец panel_thickness при откате миграции
    op.drop_column('orders', 'panel_thickness') 