from sqlalchemy import create_engine, inspect, MetaData
import os

# Connect to database
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
inspector = inspect(engine)

# Check order_joints table structure
print("Order Joints Table Structure:")
columns = inspector.get_columns('order_joints')
for column in columns:
    print(f"Column: {column['name']}, Type: {column['type']}")

# Check if joint_thickness column exists
has_thickness = any(col['name'] == 'joint_thickness' for col in columns)
print(f"\nDoes joint_thickness column exist? {has_thickness}")

# Check if there are any rows
with engine.connect() as connection:
    result = connection.execute("SELECT COUNT(*) FROM order_joints")
    count = result.scalar()
    print(f"\nNumber of rows in order_joints: {count}") 