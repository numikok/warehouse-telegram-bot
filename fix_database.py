import os
from sqlalchemy import create_engine, text

# Get database URL from environment variable
DATABASE_URL = os.environ.get('DATABASE_URL')

# Modify the URL for newer versions of sqlalchemy
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://')

print(f"Connecting to database...")
engine = create_engine(DATABASE_URL)

# SQL commands to run
sql_commands = [
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_name = 'panels' AND column_name = 'thickness'
        ) THEN
            ALTER TABLE panels ADD COLUMN thickness FLOAT DEFAULT 0.5;
            
            -- Copy data from panel_thickness if it exists
            IF EXISTS (
                SELECT FROM information_schema.columns 
                WHERE table_name = 'panels' AND column_name = 'panel_thickness'
            ) THEN
                UPDATE panels SET thickness = panel_thickness;
            END IF;
        END IF;
        
        -- Remove thickness column from films table if it exists
        IF EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_name = 'films' AND column_name = 'thickness'
        ) THEN
            ALTER TABLE films DROP COLUMN thickness;
        END IF;
    END
    $$;
    """
]

with engine.connect() as connection:
    for sql in sql_commands:
        print(f"Executing SQL: {sql[:50]}...")
        connection.execute(text(sql))
        connection.commit()

print("Database structure fixed successfully!") 