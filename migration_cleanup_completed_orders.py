import os
from sqlalchemy import create_engine, text
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Получаем строку подключения из переменной окружения
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

if not DATABASE_URL:
    logger.error("DATABASE_URL не указан в переменных окружения")
    exit(1)

# Создаем подключение к базе данных
engine = create_engine(DATABASE_URL)

def execute_sql(sql, params=None):
    with engine.connect() as connection:
        try:
            connection.execute(text(sql), params or {})
            connection.commit()
            logger.info(f"SQL успешно выполнен: {sql}")
        except Exception as e:
            connection.rollback()
            logger.error(f"Ошибка при выполнении SQL: {e}")
            raise

def check_column_exists(table_name, column_name):
    """Проверяет существование колонки в таблице"""
    sql = """
    SELECT COUNT(*) 
    FROM information_schema.columns 
    WHERE table_name = :table_name AND column_name = :column_name
    """
    with engine.connect() as connection:
        result = connection.execute(text(sql), {"table_name": table_name, "column_name": column_name})
        count = result.scalar()
        return count > 0

def drop_column_if_exists(table_name, column_name):
    """Удаляет колонку из таблицы, если она существует"""
    if check_column_exists(table_name, column_name):
        logger.info(f"Удаление колонки {column_name} из таблицы {table_name}")
        execute_sql(f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS {column_name}")
    else:
        logger.info(f"Колонка {column_name} не существует в таблице {table_name}, пропускаем")

def main():
    """Главная функция для выполнения миграции"""
    logger.info("Начало миграции: удаление ненужных колонок из таблицы completed_orders")
    
    # Список колонок для удаления
    columns_to_remove = [
        "panel_quantity",
        "joint_type",
        "joint_color",
        "joint_quantity",
        "glue_quantity",
        "panel_thickness",
        "film_code"  # Удаляем также film_code, так как теперь информация о пленке хранится в таблице completed_order_items
    ]
    
    try:
        # Удаляем каждую колонку, если она существует
        for column in columns_to_remove:
            drop_column_if_exists("completed_orders", column)
        
        logger.info("Миграция успешно завершена")
    except Exception as e:
        logger.error(f"Ошибка при выполнении миграции: {e}")

def run_migration():
    # Получение URL базы данных
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        logger.error("DATABASE_URL не указан в переменных окружения")
        logger.info("Эту миграцию необходимо выполнить на сервере Heroku.")
        logger.info("Выполните команду: heroku run python migration_cleanup_completed_orders.py")
        return
    
    # Исправление для Heroku: преобразование postgres:// в postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    logger.info(f"Connecting to database for migration...")
    
    # Создание движка SQLAlchemy
    engine = create_engine(database_url)
    
    try:
        with engine.connect() as connection:
            # Начинаем транзакцию
            with connection.begin():
                # Проверяем, существуют ли колонки, которые нужно удалить
                logger.info("Checking if columns exist in the completed_order_items table...")
                
                # Проверка колонки Product_id
                product_id_exists = connection.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'completed_order_items' AND column_name = 'product_id'"
                )).fetchone() is not None
                
                # Проверка колонки Film_ID
                film_id_exists = connection.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'completed_order_items' AND column_name = 'film_id'"
                )).fetchone() is not None
                
                # Проверка колонки Item_type
                item_type_exists = connection.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'completed_order_items' AND column_name = 'item_type'"
                )).fetchone() is not None
                
                # Проверка колонки color
                color_exists = connection.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'completed_order_items' AND column_name = 'color'"
                )).fetchone() is not None
                
                # Удаление колонок, если они существуют
                if product_id_exists:
                    logger.info("Dropping Product_id column...")
                    connection.execute(text("ALTER TABLE completed_order_items DROP COLUMN product_id"))
                
                if film_id_exists:
                    logger.info("Dropping Film_ID column...")
                    connection.execute(text("ALTER TABLE completed_order_items DROP COLUMN film_id"))
                
                if item_type_exists:
                    logger.info("Dropping Item_type column...")
                    connection.execute(text("ALTER TABLE completed_order_items DROP COLUMN item_type"))
                
                # Добавление колонки color, если она не существует
                if not color_exists:
                    logger.info("Adding color column...")
                    connection.execute(text("ALTER TABLE completed_order_items ADD COLUMN color VARCHAR NOT NULL DEFAULT 'Неизвестно'"))
                
                logger.info("Migration completed successfully!")
                
    except Exception as e:
        logger.error(f"Error during migration: {e}")
        raise
    
if __name__ == "__main__":
    run_migration() 