"""add status to completed_orders

Revision ID: 555e1a4b3c2d
Revises: 43ce81895603
Create Date: 2025-04-26 10:00:00.000000 # Placeholder date

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Import the enum from the models file
from models import CompletedOrderStatus


# revision identifiers, used by Alembic.
revision: str = '555e1a4b3c2d'
down_revision: Union[str, None] = '43ce81895603'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Define the enum type for use in the migration
completed_order_status = postgresql.ENUM(CompletedOrderStatus, name='completedorderstatus')

def upgrade() -> None:
    # Create the ENUM type in PostgreSQL if it doesn't exist
    completed_order_status.create(op.get_bind(), checkfirst=True)
    
    # Add the status column, initially allowing NULLs
    op.add_column('completed_orders', sa.Column('status', completed_order_status, nullable=True))
    
    # Update existing rows to the default status, casting the string to the enum type
    op.execute(f"UPDATE completed_orders SET status = '{CompletedOrderStatus.COMPLETED.value}'::completedorderstatus")
    
    # Now make the column NOT NULL
    op.alter_column('completed_orders', 'status', nullable=False)
    
    # Removed server_default setting for now
    # op.alter_column('completed_orders', 'status', server_default=CompletedOrderStatus.COMPLETED.value)


def downgrade() -> None:
    # Drop the status column from completed_orders
    op.drop_column('completed_orders', 'status')
    # Drop the ENUM type from PostgreSQL
    completed_order_status.drop(op.get_bind(), checkfirst=False) 