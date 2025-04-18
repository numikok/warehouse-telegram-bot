from sqlalchemy import create_engine, text
from database import DATABASE_URL
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_operations_schema():
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # Get table schema
        result = conn.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'operations'
            ORDER BY ordinal_position;
        """))
        
        logger.info("\nOperations table schema:")
        for row in result:
            logger.info(f"Column: {row[0]}, Type: {row[1]}, Nullable: {row[2]}")
        
        # Get foreign keys
        result = conn.execute(text("""
            SELECT
                tc.constraint_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM
                information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
            WHERE tc.table_name = 'operations' AND tc.constraint_type = 'FOREIGN KEY';
        """))
        
        logger.info("\nForeign keys:")
        for row in result:
            logger.info(f"Constraint: {row[0]}, Column: {row[1]} -> {row[2]}.{row[3]}")

if __name__ == "__main__":
    check_operations_schema() 