"""Add OrderProduct and OrderGlue models

Revision ID: 60c28fc06786
Revises: 9bad76da2c25
Create Date: 2025-04-18 21:28:19.294424

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '60c28fc06786'
down_revision: Union[str, None] = '9bad76da2c25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add READY_PRODUCT_OUT, JOINT_OUT, and GLUE_OUT to OperationType enum
    # Note: Enum modifications are complex, but as enum is used as String in the columns,
    # we don't need to modify the database schema for this.
    
    # Add CREATED to OrderStatus enum
    # Same as above, no schema changes needed as it's stored as String
    
    # Create order_products table
    try:
        op.create_table('order_products',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('order_id', sa.Integer(), nullable=False),
            sa.Column('film_id', sa.Integer(), nullable=False),
            sa.Column('thickness', sa.Float(), nullable=False, server_default='0.5'),
            sa.Column('quantity', sa.Integer(), nullable=False),
            sa.Column('is_finished', sa.Boolean(), nullable=False, server_default='true'),
            sa.ForeignKeyConstraint(['film_id'], ['films.id'], ),
            sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        print("Таблица order_products успешно создана")
    except Exception as e:
        print(f"Ошибка при создании таблицы order_products: {e}")
    
    # Create order_glue table
    try:
        op.create_table('order_glue',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('order_id', sa.Integer(), nullable=False),
            sa.Column('glue_id', sa.Integer(), nullable=False),
            sa.Column('quantity', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['glue_id'], ['glue.id'], ),
            sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        print("Таблица order_glue успешно создана")
    except Exception as e:
        print(f"Ошибка при создании таблицы order_glue: {e}")


def downgrade() -> None:
    # Drop order_glue table
    op.drop_table('order_glue')
    
    # Drop order_products table
    op.drop_table('order_products') 