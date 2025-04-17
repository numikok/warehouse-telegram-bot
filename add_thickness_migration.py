import os
from sqlalchemy import create_engine, Column, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from alembic import op
import sqlalchemy as sa
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get the database URL from environment variable
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Create engine and connect
engine = create_engine(DATABASE_URL)
conn = engine.connect()

# Add the thickness column if it doesn't exist
try:
    print("Adding thickness column to films table...")
    conn.execute("ALTER TABLE films ADD COLUMN IF NOT EXISTS thickness FLOAT DEFAULT 0.5 NOT NULL")
    conn.execute("COMMIT")
    print("Column added successfully!")
except Exception as e:
    print(f"Error adding column: {e}")
    conn.execute("ROLLBACK")

# Close the connection
conn.close()
print("Migration complete!") 