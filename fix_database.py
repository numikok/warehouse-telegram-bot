import os
import sys
from sqlalchemy import create_engine, MetaData, Table, Column, Float, Integer, String, ForeignKey, Enum
from sqlalchemy.sql import text
from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env
load_dotenv()

# Получить URL базы данных из переменных окружения
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

print(f"URL базы данных: {DATABASE_URL}")

# Создать подключение к базе данных
engine = create_engine(DATABASE_URL)

# Для запросов SQL
with engine.connect() as connection:
    # Убеждаемся, что пользуемся новыми транзакциями
    connection.execution_options(isolation_level="AUTOCOMMIT")
    
    # 1. Проверяем существование таблицы order_joints и создаем её при необходимости
    try:
        result = connection.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'order_joints'
            )
        """))
        table_exists = result.scalar()
        
        if not table_exists:
            print("Создаем таблицу order_joints...")
            connection.execute(text("""
                CREATE TABLE order_joints (
                    id SERIAL PRIMARY KEY,
                    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                    joint_type VARCHAR NOT NULL,
                    joint_color VARCHAR NOT NULL,
                    quantity INTEGER NOT NULL,
                    joint_thickness FLOAT NOT NULL DEFAULT 0.5
                )
            """))
            print("Таблица order_joints успешно создана")
        else:
            print("Таблица order_joints уже существует")
            
            # Проверяем наличие столбца joint_thickness
            result = connection.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'order_joints' AND column_name = 'joint_thickness'
            """))
            if not result.fetchone():
                connection.execute(text("ALTER TABLE order_joints ADD COLUMN joint_thickness FLOAT NOT NULL DEFAULT 0.5"))
                print("Столбец joint_thickness добавлен в таблицу order_joints")
            else:
                print("Столбец joint_thickness уже существует в таблице order_joints")
    except Exception as e:
        print(f"Ошибка при работе с таблицей order_joints: {e}")
    
    # 2. Проверяем существование таблицы order_items и создаем её при необходимости
    try:
        result = connection.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'order_items'
            )
        """))
        table_exists = result.scalar()
        
        if not table_exists:
            print("Создаем таблицу order_items...")
            connection.execute(text("""
                CREATE TABLE order_items (
                    id SERIAL PRIMARY KEY,
                    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                    product_id INTEGER REFERENCES finished_products(id),
                    quantity INTEGER NOT NULL,
                    color VARCHAR NOT NULL,
                    thickness FLOAT NOT NULL DEFAULT 0.5
                )
            """))
            print("Таблица order_items успешно создана")
        else:
            print("Таблица order_items уже существует")
    except Exception as e:
        print(f"Ошибка при работе с таблицей order_items: {e}")
    
    # 3. Проверяем существование таблицы order_glues и создаем её при необходимости
    try:
        result = connection.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'order_glues'
            )
        """))
        table_exists = result.scalar()
        
        if not table_exists:
            print("Создаем таблицу order_glues...")
            connection.execute(text("""
                CREATE TABLE order_glues (
                    id SERIAL PRIMARY KEY,
                    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                    quantity INTEGER NOT NULL
                )
            """))
            print("Таблица order_glues успешно создана")
        else:
            print("Таблица order_glues уже существует")
            
            # Проверяем наличие столбца glue_id и удаляем его, если он существует
            result = connection.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'order_glues' AND column_name = 'glue_id'
            """))
            if result.fetchone():
                connection.execute(text("ALTER TABLE order_glues DROP COLUMN glue_id"))
                print("Столбец glue_id удалён из таблицы order_glues")
            else:
                print("Столбец glue_id не существует в таблице order_glues")
    except Exception as e:
        print(f"Ошибка при работе с таблицей order_glues: {e}")
    
    # 4. Проверяем существование таблицы completed_order_joints и создаем её при необходимости
    try:
        result = connection.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'completed_order_joints'
            )
        """))
        table_exists = result.scalar()
        
        if not table_exists:
            print("Создаем таблицу completed_order_joints...")
            connection.execute(text("""
                CREATE TABLE completed_order_joints (
                    id SERIAL PRIMARY KEY,
                    order_id INTEGER NOT NULL REFERENCES completed_orders(id) ON DELETE CASCADE,
                    joint_type VARCHAR NOT NULL,
                    joint_color VARCHAR NOT NULL,
                    quantity INTEGER NOT NULL,
                    joint_thickness FLOAT NOT NULL DEFAULT 0.5
                )
            """))
            print("Таблица completed_order_joints успешно создана")
        else:
            print("Таблица completed_order_joints уже существует")
            
            # Проверяем наличие столбца joint_thickness
            result = connection.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'completed_order_joints' AND column_name = 'joint_thickness'
            """))
            if not result.fetchone():
                connection.execute(text("ALTER TABLE completed_order_joints ADD COLUMN joint_thickness FLOAT NOT NULL DEFAULT 0.5"))
                print("Столбец joint_thickness добавлен в таблицу completed_order_joints")
            else:
                print("Столбец joint_thickness уже существует в таблице completed_order_joints")
    except Exception as e:
        print(f"Ошибка при работе с таблицей completed_order_joints: {e}")

print("Обновление структуры базы данных завершено!") 