from sqlalchemy import create_engine, inspect, text
import os

# Connect to database
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
inspector = inspect(engine)

# List all tables
print("All tables in the database:")
tables = inspector.get_table_names()
for table in tables:
    print(f"- {table}")

# Check for any joint-related tables
print("\nSearching for tables with 'joint' in the name (case-insensitive):")
with engine.connect() as connection:
    result = connection.execute(text("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name ILIKE '%joint%'
    """))
    joint_tables = result.fetchall()
    if joint_tables:
        for table in joint_tables:
            print(f"- {table[0]}")
    else:
        print("No tables with 'joint' in the name found")

# Check for any order_joints table specifically
print("\nDetailed check for order_joints table:")
with engine.connect() as connection:
    result = connection.execute(text("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name ILIKE 'order_joints'
    """))
    order_joints = result.fetchall()
    if order_joints:
        print(f"Table found: {order_joints[0][0]}")
        
        # Check columns in the table
        result = connection.execute(text(f"""
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_name = '{order_joints[0][0]}'
            ORDER BY ordinal_position
        """))
        columns = result.fetchall()
        print("\nColumns in the table:")
        for col in columns:
            print(f"- {col[0]}: {col[1]}{f'({col[2]})' if col[2] else ''}")
    else:
        print("No order_joints table found") 