import os
from sqlalchemy import create_engine, text, MetaData, Table, Column, Integer, String, Float, ForeignKey, Boolean

# Получить URL базы данных из переменных окружения
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Создать подключение к базе данных
engine = create_engine(DATABASE_URL)

with engine.connect() as connection:
    # Используем AUTOCOMMIT для непосредственного применения изменений
    connection.execution_options(isolation_level="AUTOCOMMIT")
    
    print("Начинаем создание таблицы order_items...")
    
    try:
        # Проверяем, существует ли уже таблица order_items
        result = connection.execute(text("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = 'order_items'
        """))
        
        if not result.fetchone():
            # Создаем таблицу order_items
            connection.execute(text("""
                CREATE TABLE order_items (
                    id SERIAL PRIMARY KEY,
                    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                    item_type VARCHAR(20) NOT NULL, -- 'product' или 'film'
                    product_id INTEGER, -- ID продукта, если item_type = 'product'
                    film_id INTEGER, -- ID пленки, если item_type = 'film'
                    film_thickness FLOAT, -- Толщина пленки, если item_type = 'film'
                    quantity INTEGER NOT NULL,
                    FOREIGN KEY (product_id) REFERENCES finished_products(id) ON DELETE CASCADE,
                    FOREIGN KEY (film_id) REFERENCES films(id) ON DELETE CASCADE,
                    CHECK ((item_type = 'product' AND product_id IS NOT NULL AND film_id IS NULL AND film_thickness IS NULL) OR 
                           (item_type = 'film' AND film_id IS NOT NULL AND product_id IS NULL))
                )
            """))
            
            print("Таблица order_items успешно создана")
            
            # Если нужно создать аналогичную таблицу для завершенных заказов
            result = connection.execute(text("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'completed_order_items'
            """))
            
            if not result.fetchone():
                connection.execute(text("""
                    CREATE TABLE completed_order_items (
                        id SERIAL PRIMARY KEY,
                        completed_order_id INTEGER NOT NULL REFERENCES completed_orders(id) ON DELETE CASCADE,
                        item_type VARCHAR(20) NOT NULL, -- 'product' или 'film'
                        product_id INTEGER, -- ID продукта, если item_type = 'product'
                        film_id INTEGER, -- ID пленки, если item_type = 'film'
                        film_thickness FLOAT, -- Толщина пленки, если item_type = 'film'
                        quantity INTEGER NOT NULL,
                        FOREIGN KEY (product_id) REFERENCES finished_products(id) ON DELETE CASCADE,
                        FOREIGN KEY (film_id) REFERENCES films(id) ON DELETE CASCADE,
                        CHECK ((item_type = 'product' AND product_id IS NOT NULL AND film_id IS NULL AND film_thickness IS NULL) OR 
                               (item_type = 'film' AND film_id IS NOT NULL AND product_id IS NULL))
                    )
                """))
                
                print("Таблица completed_order_items успешно создана")
            else:
                print("Таблица completed_order_items уже существует")
        else:
            print("Таблица order_items уже существует")
        
        # Также проверяем и удаляем столбец is_finished из таблицы order_items, если он существует
        # (этот шаг соответствует оригинальному fix_database.py)
        result = connection.execute(text("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'order_items' AND column_name = 'is_finished'
        """))
        if result.fetchone():
            connection.execute(text("ALTER TABLE order_items DROP COLUMN is_finished"))
            print("Столбец is_finished удален из таблицы order_items")
        else:
            print("Столбец is_finished не существует в таблице order_items")
        
        # Проверяем и удаляем столбец glue_id в таблице order_glues
        result = connection.execute(text("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'order_glues' AND column_name = 'glue_id'
        """))
        if result.fetchone():
            connection.execute(text("ALTER TABLE order_glues DROP COLUMN glue_id"))
            print("Столбец glue_id удален из таблицы order_glues")
        else:
            print("Столбец glue_id не существует в таблице order_glues")
        
        # Проверяем и удаляем столбец glue_id в таблице completed_order_glues
        result = connection.execute(text("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'completed_order_glues' AND column_name = 'glue_id'
        """))
        if result.fetchone():
            connection.execute(text("ALTER TABLE completed_order_glues DROP COLUMN glue_id"))
            print("Столбец glue_id удален из таблицы completed_order_glues")
        else:
            print("Столбец glue_id не существует в таблице completed_order_glues")
        
        print("Все операции успешно выполнены!")
        
    except Exception as e:
        print(f"Ошибка при выполнении операций: {e}")
        raise 