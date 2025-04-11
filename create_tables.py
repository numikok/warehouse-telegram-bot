import os
import logging
from sqlalchemy import create_engine
from models import Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_tables():
    # Получение URL базы данных
    database_url = os.getenv("DATABASE_URL")
    
    # Исправление для Heroku: преобразование postgres:// в postgresql://
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    logger.info(f"Connecting to database...")
    
    # Создание движка SQLAlchemy
    engine = create_engine(database_url)
    
    try:
        # Создание всех таблиц
        Base.metadata.create_all(engine)
        logger.info("Tables successfully created!")
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        raise
    
if __name__ == "__main__":
    create_tables() 