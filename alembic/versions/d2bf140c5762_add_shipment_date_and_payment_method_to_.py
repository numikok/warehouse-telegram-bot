"""add shipment_date and payment_method to orders

Revision ID: d2bf140c5762
Revises: 60c28fc06786
Create Date: 2025-04-25 18:46:41.093354

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2bf140c5762'
down_revision: Union[str, None] = '60c28fc06786'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('orders', sa.Column('shipment_date', sa.Date(), nullable=True))
    op.add_column('orders', sa.Column('payment_method', sa.String(length=50), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('orders', 'payment_method')
    op.drop_column('orders', 'shipment_date')
    # ### end Alembic commands ### 