from sqlalchemy import create_engine, inspect, text
import os

# Connect to database
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
inspector = inspect(engine)

# List all tables again to check if order_items is there
print("All tables in the database:")
tables = inspector.get_table_names()
for table in tables:
    print(f"- {table}")

# Check for order_items table specifically
if 'order_items' in tables:
    print("\nDetailed check for order_items table:")
    # Check columns in the table
    columns = inspector.get_columns('order_items')
    print("Columns in the table:")
    for col in columns:
        print(f"- {col['name']}: {col['type']}")
    
    # Check constraints
    constraints = inspector.get_check_constraints('order_items')
    print("\nCheck constraints:")
    for constraint in constraints:
        print(f"- {constraint['name']}: {constraint['sqltext']}")
    
    # Check foreign keys
    foreign_keys = inspector.get_foreign_keys('order_items')
    print("\nForeign keys:")
    for fk in foreign_keys:
        print(f"- {fk['name'] if 'name' in fk else 'unnamed'}: {fk['referred_table']}({', '.join(fk['referred_columns'])})")
else:
    print("\norder_items table not found!")

# Also check for completed_order_items table
if 'completed_order_items' in tables:
    print("\nDetailed check for completed_order_items table:")
    # Check columns in the table
    columns = inspector.get_columns('completed_order_items')
    print("Columns in the table:")
    for col in columns:
        print(f"- {col['name']}: {col['type']}")
else:
    print("\ncompleted_order_items table not found!") 