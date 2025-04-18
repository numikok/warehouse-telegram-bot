"""Update operation_type to use strings instead of enum

Revision ID: update_operation_type
Revises: 753906409270
Create Date: 2024-03-24 15:15:24.903377

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'update_operation_type'
down_revision: Union[str, None] = '753906409270'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Get the list of existing foreign key constraints
    conn = op.get_bind()
    result = conn.execute(text("""
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'operations'::regclass
        AND contype = 'f'
    """))
    existing_constraints = [row[0] for row in result]
    
    # Drop existing foreign key constraints
    for constraint in existing_constraints:
        op.drop_constraint(constraint, 'operations', type_='foreignkey')
    
    # Drop the primary key constraint if it exists
    conn.execute(text("""
        DO $$ 
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'operations_pkey'
                AND conrelid = 'operations'::regclass
            ) THEN
                ALTER TABLE operations DROP CONSTRAINT operations_pkey;
            END IF;
        END $$;
    """))
    
    # Create a temporary table with the new schema
    op.create_table(
        'operations_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('operation_type', sa.String(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.Column('details', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Copy data from old table to new table
    op.execute("""
        INSERT INTO operations_new (id, user_id, operation_type, quantity, timestamp, details)
        SELECT id, user_id, operation_type, quantity, timestamp, details
        FROM operations
    """)
    
    # Drop the old table
    op.drop_table('operations')
    
    # Rename the new table to the original name
    op.rename_table('operations_new', 'operations')
    
    # Recreate the foreign key constraints
    op.create_foreign_key('operations_user_id_fkey', 'operations', 'users', ['user_id'], ['id'])
    
    # Drop the old enum type if it exists
    op.execute("""
        DO $$ 
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'operationtype') THEN
                DROP TYPE operationtype;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Create the enum type
    op.execute("""
        CREATE TYPE operationtype AS ENUM ('INCOME', 'PRODUCTION', 'SALE', 'WAREHOUSE')
    """)
    
    # Create a temporary table with the old schema
    op.create_table(
        'operations_old',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('type', sa.Enum('INCOME', 'PRODUCTION', 'SALE', 'WAREHOUSE', name='operationtype'), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('color_id', sa.Integer(), nullable=True),
        sa.Column('panel_id', sa.Integer(), nullable=True),
        sa.Column('film_id', sa.Integer(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Copy data from new table to old table, converting strings to enum values
    op.execute("""
        INSERT INTO operations_old (id, type, user_id, color_id, panel_id, film_id, quantity, created_at)
        SELECT id, 
               CASE operation_type
                   WHEN 'film_income' THEN 'INCOME'
                   WHEN 'production' THEN 'PRODUCTION'
                   WHEN 'order' THEN 'SALE'
                   WHEN 'warehouse' THEN 'WAREHOUSE'
                   ELSE NULL
               END,
               user_id, NULL, NULL, NULL, quantity, timestamp
        FROM operations
    """)
    
    # Drop the new table
    op.drop_table('operations')
    
    # Rename the old table to the original name
    op.rename_table('operations_old', 'operations')
    
    # Recreate the foreign key constraints
    op.create_foreign_key('operations_user_id_fkey', 'operations', 'users', ['user_id'], ['id'])
    op.create_foreign_key('operations_color_id_fkey', 'operations', 'colors', ['color_id'], ['id'])
    op.create_foreign_key('operations_film_id_fkey', 'operations', 'film', ['film_id'], ['id'])
    op.create_foreign_key('operations_panel_id_fkey', 'operations', 'panels', ['panel_id'], ['id']) 