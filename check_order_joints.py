import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get database URL from environment variables
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

print(f"Database URL: {DATABASE_URL}")

# Create a connection to the database
engine = create_engine(DATABASE_URL)

# For SQL queries
with engine.connect() as connection:
    # Get column names for order_items table
    print("Columns in order_items table:")
    columns = connection.execute(text("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'order_items'
    """))
    
    for column in columns:
        print(f"  {column.column_name}: {column.data_type}") 