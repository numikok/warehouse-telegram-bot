"""Fix order tables structure

Revision ID: fix_order_tables_structure
Revises: None
Create Date: 2025-05-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Column, Integer, String, Float, ForeignKey

# revision identifiers, used by Alembic.
revision: str = 'fix_order_tables_structure'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Проверяем и удаляем таблицу order_films
    try:
        op.drop_table('order_films')
        print("Dropped order_films table")
    except Exception as e:
        print(f"Note: {e}")
    
    try:
        op.drop_table('completed_order_films')
        print("Dropped completed_order_films table")
    except Exception as e:
        print(f"Note: {e}")
    
    # 2. Проверяем и удаляем таблицу order_products
    try:
        op.drop_table('order_products')
        print("Dropped order_products table")
    except Exception as e:
        print(f"Note: {e}")
    
    # 3. Проверяем наличие столбца joint_thickness в таблице order_joints
    # Этот столбец уже должен существовать, но на всякий случай проверим
    # И если его нет, добавим
    with op.batch_alter_table('order_joints') as batch_op:
        try:
            batch_op.add_column(Column('joint_thickness', Float, nullable=False, server_default='0.5'))
            print("Added joint_thickness column to order_joints table")
        except Exception as e:
            # Столбец уже существует, пропускаем
            print(f"Note: {e}")
            pass
    
    with op.batch_alter_table('completed_order_joints') as batch_op:
        try:
            batch_op.add_column(Column('joint_thickness', Float, nullable=False, server_default='0.5'))
            print("Added joint_thickness column to completed_order_joints table")
        except Exception as e:
            # Столбец уже существует, пропускаем
            print(f"Note: {e}")
            pass
            
    # 4. Убедимся, что в таблице order_items нет столбца is_finished
    # Если он есть, удалим его
    with op.batch_alter_table('order_items') as batch_op:
        try:
            batch_op.drop_column('is_finished')
            print("Removed is_finished column from order_items table")
        except Exception as e:
            # Столбец не существует, пропускаем
            print(f"Note: {e}")
            pass
    
    # 5. Убедимся, что в таблице order_glues нет столбца glue_id
    # Этот столбец уже должен отсутствовать, так как в модели его нет

def downgrade() -> None:
    # Восстановление таблицы order_films
    op.create_table('order_films',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('film_code', sa.String(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False)
    )
    
    op.create_table('completed_order_films',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('completed_orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('film_code', sa.String(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False)
    )
    
    # Восстановление таблицы order_products
    op.create_table('order_products',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('film_id', sa.Integer(), sa.ForeignKey('films.id'), nullable=False),
        sa.Column('thickness', sa.Float(), nullable=False, server_default='0.5'),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('is_finished', sa.Boolean(), nullable=False, server_default='true')
    )
    
    # Добавим is_finished к order_items
    with op.batch_alter_table('order_items') as batch_op:
        batch_op.add_column(sa.Column('is_finished', sa.Boolean(), nullable=False, server_default='true')) 