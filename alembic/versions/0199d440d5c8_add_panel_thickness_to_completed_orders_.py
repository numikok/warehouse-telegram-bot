"""add_panel_thickness_to_completed_orders_table

Revision ID: 0199d440d5c8
Revises: 5093edd4cb47
Create Date: 2025-04-18 20:21:58.378696

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0199d440d5c8'
down_revision: Union[str, None] = '5093edd4cb47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем столбец panel_thickness в таблицу completed_orders с дефолтным значением 0.5
    op.add_column('completed_orders', sa.Column('panel_thickness', sa.Float(), nullable=False, server_default='0.5'))


def downgrade() -> None:
    # Удаляем столбец panel_thickness при откате миграции
    op.drop_column('completed_orders', 'panel_thickness') 