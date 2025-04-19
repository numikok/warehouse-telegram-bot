import os
from sqlalchemy import create_engine, MetaData, Table, Column, Float
from sqlalchemy.sql import text

# Получить URL базы данных из переменных окружения
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Создать подключение к базе данных
engine = create_engine(DATABASE_URL)

# Для запросов SQL
with engine.connect() as connection:
    # 1. Удаление таблицы order_films, если она существует
    try:
        connection.execute(text("DROP TABLE IF EXISTS order_films CASCADE"))
        print("Таблица order_films удалена (или не существовала)")
    except Exception as e:
        print(f"Ошибка при удалении таблицы order_films: {e}")
    
    # 2. Удаление таблицы completed_order_films, если она существует
    try:
        connection.execute(text("DROP TABLE IF EXISTS completed_order_films CASCADE"))
        print("Таблица completed_order_films удалена (или не существовала)")
    except Exception as e:
        print(f"Ошибка при удалении таблицы completed_order_films: {e}")
    
    # 3. Удаление таблицы order_products, если она существует
    try:
        connection.execute(text("DROP TABLE IF EXISTS order_products CASCADE"))
        print("Таблица order_products удалена (или не существовала)")
    except Exception as e:
        print(f"Ошибка при удалении таблицы order_products: {e}")
    
    # 4. Проверка наличия и добавление столбца joint_thickness в таблицу order_joints
    try:
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
        print(f"Ошибка при проверке/добавлении столбца joint_thickness в таблицу order_joints: {e}")
    
    # 5. Проверка наличия и добавление столбца joint_thickness в таблицу completed_order_joints
    try:
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
        print(f"Ошибка при проверке/добавлении столбца joint_thickness в таблицу completed_order_joints: {e}")
    
    # 6. Проверка наличия и удаление столбца is_finished в таблице order_items
    try:
        result = connection.execute(text("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'order_items' AND column_name = 'is_finished'
        """))
        if result.fetchone():
            connection.execute(text("ALTER TABLE order_items DROP COLUMN is_finished"))
            print("Столбец is_finished удален из таблицы order_items")
        else:
            print("Столбец is_finished не существует в таблице order_items")
    except Exception as e:
        print(f"Ошибка при проверке/удалении столбца is_finished из таблицы order_items: {e}")
    
    # 7. Проверка наличия и удаление столбца glue_id в таблице order_glues
    try:
        result = connection.execute(text("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'order_glues' AND column_name = 'glue_id'
        """))
        if result.fetchone():
            connection.execute(text("ALTER TABLE order_glues DROP COLUMN glue_id"))
            print("Столбец glue_id удален из таблицы order_glues")
        else:
            print("Столбец glue_id не существует в таблице order_glues")
    except Exception as e:
        print(f"Ошибка при проверке/удалении столбца glue_id из таблицы order_glues: {e}")
    
    # 8. Проверка наличия и удаление столбца glue_id в таблице completed_order_glues
    try:
        result = connection.execute(text("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'completed_order_glues' AND column_name = 'glue_id'
        """))
        if result.fetchone():
            connection.execute(text("ALTER TABLE completed_order_glues DROP COLUMN glue_id"))
            print("Столбец glue_id удален из таблицы completed_order_glues")
        else:
            print("Столбец glue_id не существует в таблице completed_order_glues")
    except Exception as e:
        print(f"Ошибка при проверке/удалении столбца glue_id из таблицы completed_order_glues: {e}")

print("Обновление структуры базы данных завершено!") 