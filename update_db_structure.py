import os
from sqlalchemy import create_engine, text

# Получить URL базы данных из переменных окружения
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Создать подключение к базе данных
engine = create_engine(DATABASE_URL)

with engine.connect() as connection:
    # Используем AUTOCOMMIT для непосредственного применения изменений
    connection.execution_options(isolation_level="AUTOCOMMIT")
    
    print("Начинаем обновление структуры базы данных...")
    
    try:
        # 1. Обновление таблицы orders
        print("\n1. Обновление таблицы orders...")
        
        # Сначала получим список столбцов, которые нужно оставить
        needed_columns = ["id", "manager_id", "customer_phone", "delivery_address", "installation_required", 
                         "status", "created_at", "updated_at", "completed_at"]
        
        # Получаем текущие столбцы таблицы orders
        result = connection.execute(text("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name = 'orders'
        """))
        current_columns = [row[0] for row in result.fetchall()]
        
        # Проверяем, каких столбцов не хватает и добавляем их
        for column in needed_columns:
            if column not in current_columns:
                if column == "manager_id":
                    connection.execute(text(f"ALTER TABLE orders ADD COLUMN {column} INTEGER"))
                elif column in ["customer_phone", "delivery_address", "status"]:
                    connection.execute(text(f"ALTER TABLE orders ADD COLUMN {column} VARCHAR"))
                elif column == "installation_required":
                    connection.execute(text(f"ALTER TABLE orders ADD COLUMN {column} BOOLEAN DEFAULT FALSE"))
                elif column in ["created_at", "updated_at", "completed_at"]:
                    connection.execute(text(f"ALTER TABLE orders ADD COLUMN {column} TIMESTAMP"))
                print(f"Добавлен столбец {column} в таблицу orders")
        
        # Удаляем лишние столбцы
        for column in current_columns:
            if column not in needed_columns:
                connection.execute(text(f"ALTER TABLE orders DROP COLUMN IF EXISTS {column}"))
                print(f"Удален столбец {column} из таблицы orders")
        
        # 2. Обновление таблицы order_items
        print("\n2. Обновление таблицы order_items...")
        
        # Пересоздаем таблицу order_items
        connection.execute(text("DROP TABLE IF EXISTS order_items CASCADE"))
        connection.execute(text("""
            CREATE TABLE order_items (
                id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                color VARCHAR,
                thickness FLOAT,
                quantity INTEGER NOT NULL
            )
        """))
        print("Таблица order_items пересоздана с новой структурой")
        
        # 3. Обновление таблицы order_joints
        print("\n3. Обновление таблицы order_joints...")
        
        # Получаем текущие столбцы таблицы order_joints
        result = connection.execute(text("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name = 'order_joints'
        """))
        joint_columns = [row[0] for row in result.fetchall()]
        
        # Переименование столбца quantity в joint_quantity, если он существует
        if "quantity" in joint_columns and "joint_quantity" not in joint_columns:
            connection.execute(text("ALTER TABLE order_joints RENAME COLUMN quantity TO joint_quantity"))
            print("Столбец quantity переименован в joint_quantity в таблице order_joints")
        elif "joint_quantity" not in joint_columns:
            connection.execute(text("ALTER TABLE order_joints ADD COLUMN joint_quantity INTEGER"))
            print("Добавлен столбец joint_quantity в таблицу order_joints")
        
        # Удаляем лишние столбцы из order_joints
        needed_joint_columns = ["id", "order_id", "joint_type", "joint_color", "joint_thickness", "joint_quantity"]
        for column in joint_columns:
            if column not in needed_joint_columns:
                connection.execute(text(f"ALTER TABLE order_joints DROP COLUMN IF EXISTS {column}"))
                print(f"Удален столбец {column} из таблицы order_joints")
        
        # 4. Обновление таблицы order_glues
        print("\n4. Обновление таблицы order_glues...")
        
        # Проверяем, существует ли таблица order_glues
        result = connection.execute(text("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = 'order_glue'
        """))
        
        # Если таблица называется order_glue (ед. число), переименуем в order_glues
        if result.fetchone():
            connection.execute(text("ALTER TABLE order_glue RENAME TO order_glues"))
            print("Таблица order_glue переименована в order_glues")
        
        # Проверяем структуру таблицы order_glues
        result = connection.execute(text("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = 'order_glues'
        """))
        
        if not result.fetchone():
            # Создаем таблицу order_glues, если она не существует
            connection.execute(text("""
                CREATE TABLE order_glues (
                    id SERIAL PRIMARY KEY,
                    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                    quantity INTEGER NOT NULL
                )
            """))
            print("Таблица order_glues создана")
        else:
            # Получаем текущие столбцы таблицы order_glues
            result = connection.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_schema = 'public' AND table_name = 'order_glues'
            """))
            glue_columns = [row[0] for row in result.fetchall()]
            
            # Удаляем лишние столбцы
            needed_glue_columns = ["id", "order_id", "quantity"]
            for column in glue_columns:
                if column not in needed_glue_columns:
                    connection.execute(text(f"ALTER TABLE order_glues DROP COLUMN IF EXISTS {column}"))
                    print(f"Удален столбец {column} из таблицы order_glues")
            
            # Проверяем наличие необходимых столбцов
            if "order_id" not in glue_columns:
                connection.execute(text("ALTER TABLE order_glues ADD COLUMN order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE"))
                print("Добавлен столбец order_id в таблицу order_glues")
            
            if "quantity" not in glue_columns:
                connection.execute(text("ALTER TABLE order_glues ADD COLUMN quantity INTEGER NOT NULL DEFAULT 0"))
                print("Добавлен столбец quantity в таблицу order_glues")

        print("\nОбновление структуры базы данных завершено успешно!")
        
    except Exception as e:
        print(f"Ошибка при обновлении структуры базы данных: {e}")
        raise 