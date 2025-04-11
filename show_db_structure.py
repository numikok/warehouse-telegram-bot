from sqlalchemy import create_engine, text, inspect
import os
from dotenv import load_dotenv
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Получение строки подключения к БД
DATABASE_URL = os.getenv("DATABASE_URL")

# Исправление для Heroku: преобразование postgres:// в postgresql://
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Создание подключения к БД
engine = create_engine(DATABASE_URL)
inspector = inspect(engine)

def show_tables():
    """Показывает все таблицы и их структуру"""
    logger.info("\n=== Структура базы данных ===")
    
    # Получаем список всех таблиц
    tables = inspector.get_table_names()
    logger.info(f"\nНайдено таблиц: {len(tables)}")
    
    # Для каждой таблицы показываем структуру
    for table_name in tables:
        logger.info(f"\n📋 Таблица: {table_name}")
        
        # Получаем информацию о колонках
        columns = inspector.get_columns(table_name)
        logger.info("Колонки:")
        for column in columns:
            logger.info(f"  - {column['name']}: {column['type']}")
        
        # Получаем первичные ключи
        pk = inspector.get_pk_constraint(table_name)
        if pk['constrained_columns']:
            logger.info(f"Первичный ключ: {', '.join(pk['constrained_columns'])}")
        
        # Получаем внешние ключи
        fks = inspector.get_foreign_keys(table_name)
        if fks:
            logger.info("Внешние ключи:")
            for fk in fks:
                logger.info(f"  - {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}")

def show_enum_types():
    """Показывает все enum типы и их значения"""
    logger.info("\n=== Enum типы ===")
    
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT t.typname, e.enumlabel
            FROM pg_type t 
            JOIN pg_enum e ON t.oid = e.enumtypid
            ORDER BY t.typname, e.enumsortorder;
        """))
        
        current_type = None
        for row in result:
            if current_type != row[0]:
                current_type = row[0]
                logger.info(f"\n🔷 {current_type}:")
            logger.info(f"  - {row[1]}")

def show_table_contents(table_name, limit=5):
    """Показывает содержимое указанной таблицы"""
    logger.info(f"\n=== Содержимое таблицы {table_name} (первые {limit} записей) ===")
    
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT * FROM {table_name} LIMIT {limit}"))
        for row in result:
            logger.info(row)

if __name__ == "__main__":
    try:
        # Показываем структуру всех таблиц
        show_tables()
        
        # Показываем все enum типы
        show_enum_types()
        
        # Показываем содержимое некоторых важных таблиц
        important_tables = ['users', 'orders', 'finished_product']
        for table in important_tables:
            try:
                show_table_contents(table)
            except Exception as e:
                logger.warning(f"Не удалось показать содержимое таблицы {table}: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка при получении информации о базе данных: {e}") 