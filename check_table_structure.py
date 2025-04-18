import os
from sqlalchemy import create_engine, inspect, text

# Get database URL from environment variable
DATABASE_URL = os.environ.get('DATABASE_URL')

# Modify the URL for newer versions of sqlalchemy
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://')

print(f"Connecting to database...")
engine = create_engine(DATABASE_URL)

# Check table structure
inspector = inspect(engine)

# Check if panels table exists
tables = inspector.get_table_names()
print(f"Tables in database: {tables}")

if 'panels' in tables:
    print("\nColumns in 'panels' table:")
    columns = inspector.get_columns('panels')
    for column in columns:
        print(f"- {column['name']} (type: {column['type']})")
else:
    print("Table 'panels' does not exist!")

# Also check for any panel-related data
with engine.connect() as connection:
    try:
        result = connection.execute(text("SELECT * FROM panels LIMIT 5"))
        rows = result.fetchall()
        if rows:
            print("\nSample data from panels table:")
            for row in rows:
                print(row)
        else:
            print("\nNo data in panels table")
    except Exception as e:
        print(f"Error querying panels table: {e}") 