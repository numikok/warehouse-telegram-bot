"""add_film_thickness_to_models

Revision ID: 3bd7046278f0
Revises: 753906409270
Create Date: 2025-04-16 20:28:19.824792

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3bd7046278f0'
down_revision: Union[str, None] = '753906409270'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### First add nullable columns ###
    op.add_column('completed_orders', sa.Column('film_thickness', sa.Float(), nullable=True))
    op.add_column('films', sa.Column('thickness', sa.Float(), nullable=True))
    op.add_column('orders', sa.Column('film_thickness', sa.Float(), nullable=True))
    op.add_column('production_orders', sa.Column('film_thickness', sa.Float(), nullable=True))
    
    # Then update those columns with default values
    op.execute("UPDATE completed_orders SET film_thickness = 0.5")
    op.execute("UPDATE films SET thickness = 0.5")
    op.execute("UPDATE orders SET film_thickness = 0.5")
    op.execute("UPDATE production_orders SET film_thickness = 0.5")
    
    # Now make the columns NOT NULL
    op.alter_column('completed_orders', 'film_thickness', nullable=False)
    op.alter_column('films', 'thickness', nullable=False)
    op.alter_column('orders', 'film_thickness', nullable=False)
    op.alter_column('production_orders', 'film_thickness', nullable=False)
    
    # Other operations from the autogenerate
    op.alter_column('glue', 'quantity',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Integer(),
               existing_nullable=True)
    op.alter_column('operations', 'user_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('operations', 'quantity',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('users', 'telegram_id',
               existing_type=sa.BIGINT(),
               nullable=False)
    op.alter_column('users', 'username',
               existing_type=sa.VARCHAR(),
               nullable=False)
    op.alter_column('users', 'role',
               existing_type=postgresql.ENUM('SUPER_ADMIN', 'SALES_MANAGER', 'PRODUCTION', 'WAREHOUSE', 'NONE', name='userrole'),
               nullable=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('users', 'role',
               existing_type=postgresql.ENUM('SUPER_ADMIN', 'SALES_MANAGER', 'PRODUCTION', 'WAREHOUSE', 'NONE', name='userrole'),
               nullable=True)
    op.alter_column('users', 'username',
               existing_type=sa.VARCHAR(),
               nullable=True)
    op.alter_column('users', 'telegram_id',
               existing_type=sa.BIGINT(),
               nullable=True)
    op.drop_column('production_orders', 'film_thickness')
    op.drop_column('orders', 'film_thickness')
    op.alter_column('operations', 'quantity',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('operations', 'user_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('glue', 'quantity',
               existing_type=sa.Integer(),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=True)
    # Skip dropping the constraint that we didn't add
    # op.drop_constraint(None, 'finished_products', type_='foreignkey')
    op.drop_column('films', 'thickness')
    op.drop_column('completed_orders', 'film_thickness')
    # ### end Alembic commands ### 