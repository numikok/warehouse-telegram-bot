from database import get_db, engine
from models import Base, User, UserRole
import logging
import os
from dotenv import load_dotenv
from sqlalchemy import text

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reset_database():
    """Reset all data in the database while preserving the admin user."""
    try:
        # Get admin user ID from environment variables
        admin_id = int(os.getenv("ADMIN_USER_ID", 0))
        
        # Connect to database
        db = next(get_db())
        try:
            logger.info("Starting database reset...")
            
            # Get admin user before deletion if exists
            admin_user = None
            if admin_id > 0:
                admin_user = db.query(User).filter(User.telegram_id == admin_id).first()
                if admin_user:
                    logger.info(f"Found admin user: {admin_user.username} (ID: {admin_user.telegram_id})")
                else:
                    logger.warning(f"Admin user with ID {admin_id} not found")
            
            # Get all table names from metadata, sorted to respect dependencies
            metadata = Base.metadata
            
            # Disable foreign key checks for PostgreSQL
            db.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            db.commit()
            
            # Truncate all tables
            for table in reversed(metadata.sorted_tables):
                logger.info(f"Truncating table: {table.name}")
                db.execute(text(f'TRUNCATE TABLE {table.name} RESTART IDENTITY CASCADE'))
            
            # Re-enable foreign key checks
            db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            db.commit()
            
            # Recreate admin user if existed
            if admin_user:
                logger.info(f"Recreating admin user with ID {admin_id}")
                new_admin = User(
                    telegram_id=admin_id,
                    username=admin_user.username,
                    role=UserRole.SUPER_ADMIN
                )
                db.add(new_admin)
                db.commit()
                logger.info("Admin user recreated successfully")
            
            logger.info("Database reset completed successfully")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error resetting database: {e}", exc_info=True)
            raise
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Database reset failed: {e}", exc_info=True)

if __name__ == "__main__":
    reset_database()
    print("Database has been reset. All data has been cleared except for the admin user.") 