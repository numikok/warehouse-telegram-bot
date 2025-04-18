"""add_multiple_colors_and_joints_to_orders

Revision ID: 9bad76da2c25
Revises: 0199d440d5c8
Create Date: 2025-04-18 20:28:51.222289

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9bad76da2c25'
down_revision: Union[str, None] = '0199d440d5c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Создаем таблицу для связи заказов и цветов пленки
    op.create_table('order_films',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('film_code', sa.String(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Создаем таблицу для связи заказов и типов стыков
    op.create_table('order_joints',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('joint_type', sa.String(), nullable=False),
        sa.Column('joint_color', sa.String(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Создаем такие же таблицы для завершенных заказов
    op.create_table('completed_order_films',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('film_code', sa.String(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['completed_orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('completed_order_joints',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('joint_type', sa.String(), nullable=False),
        sa.Column('joint_color', sa.String(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['completed_orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    # Удаляем созданные таблицы в обратном порядке
    op.drop_table('completed_order_joints')
    op.drop_table('completed_order_films')
    op.drop_table('order_joints')
    op.drop_table('order_films') 