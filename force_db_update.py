import os
from sqlalchemy import create_engine, text

# Get database URL from environment variables
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Create database connection
engine = create_engine(DATABASE_URL)

# Direct SQL commands to make changes
with engine.connect() as connection:
    # Commit each statement directly to ensure they take effect
    connection.execution_options(isolation_level="AUTOCOMMIT")
    
    print("Starting forced database update...")
    
    try:
        # 1. Force drop tables whether they exist or not
        print("Dropping tables...")
        connection.execute(text("DROP TABLE IF EXISTS order_films CASCADE"))
        connection.execute(text("DROP TABLE IF EXISTS completed_order_films CASCADE"))
        connection.execute(text("DROP TABLE IF EXISTS order_products CASCADE"))
        
        # 2. Check if joint_thickness column exists in order_joints and add it if not
        print("Checking order_joints table...")
        result = connection.execute(text("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name = 'order_joints' AND column_name = 'joint_thickness'
        """))
        if not result.fetchone():
            print("Adding joint_thickness column to order_joints...")
            connection.execute(text("ALTER TABLE order_joints ADD COLUMN joint_thickness FLOAT DEFAULT 0.5"))
            # Set NOT NULL constraint after adding values
            connection.execute(text("UPDATE order_joints SET joint_thickness = 0.5 WHERE joint_thickness IS NULL"))
            connection.execute(text("ALTER TABLE order_joints ALTER COLUMN joint_thickness SET NOT NULL"))
            print("joint_thickness column added to order_joints")
        else:
            print("joint_thickness column already exists in order_joints")
        
        # 3. Check if joint_thickness column exists in completed_order_joints and add it if not
        print("Checking completed_order_joints table...")
        result = connection.execute(text("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name = 'completed_order_joints' AND column_name = 'joint_thickness'
        """))
        if not result.fetchone():
            print("Adding joint_thickness column to completed_order_joints...")
            connection.execute(text("ALTER TABLE completed_order_joints ADD COLUMN joint_thickness FLOAT DEFAULT 0.5"))
            # Set NOT NULL constraint after adding values
            connection.execute(text("UPDATE completed_order_joints SET joint_thickness = 0.5 WHERE joint_thickness IS NULL"))
            connection.execute(text("ALTER TABLE completed_order_joints ALTER COLUMN joint_thickness SET NOT NULL"))
            print("joint_thickness column added to completed_order_joints")
        else:
            print("joint_thickness column already exists in completed_order_joints")
        
        print("Database update completed successfully!")
    except Exception as e:
        print(f"Error updating database: {e}")
        raise 