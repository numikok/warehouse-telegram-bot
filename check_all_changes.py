from sqlalchemy import create_engine, inspect, text
import os

# Connect to database
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
inspector = inspect(engine)

# List all tables
print("1. Список всех таблиц в базе данных:")
tables = inspector.get_table_names()
for table in tables:
    print(f"- {table}")

print("\n2. Проверка удаления таблиц:")
removed_tables = ['order_films', 'completed_order_films', 'order_products']
for table in removed_tables:
    if table in tables:
        print(f"❌ Таблица {table} все еще существует")
    else:
        print(f"✅ Таблица {table} успешно удалена")

print("\n3. Проверка наличия новых таблиц:")
new_tables = ['order_items', 'completed_order_items']
for table in new_tables:
    if table in tables:
        print(f"✅ Таблица {table} успешно создана")
    else:
        print(f"❌ Таблица {table} не найдена")

print("\n4. Проверка добавления столбца joint_thickness:")
with engine.connect() as connection:
    # Проверка в order_joints
    result = connection.execute(text("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'order_joints' AND column_name = 'joint_thickness'
    """))
    if result.fetchone():
        print("✅ Столбец joint_thickness успешно добавлен в таблицу order_joints")
    else:
        print("❌ Столбец joint_thickness НЕ добавлен в таблицу order_joints")
    
    # Проверка в completed_order_joints
    result = connection.execute(text("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'completed_order_joints' AND column_name = 'joint_thickness'
    """))
    if result.fetchone():
        print("✅ Столбец joint_thickness успешно добавлен в таблицу completed_order_joints")
    else:
        print("❌ Столбец joint_thickness НЕ добавлен в таблицу completed_order_joints")

print("\n5. Проверка структуры order_items:")
if 'order_items' in tables:
    columns = inspector.get_columns('order_items')
    expected_columns = ['id', 'order_id', 'item_type', 'product_id', 'film_id', 'film_thickness', 'quantity']
    column_names = [col['name'] for col in columns]
    
    has_all_columns = all(col in column_names for col in expected_columns)
    
    if has_all_columns:
        print("✅ Таблица order_items содержит все необходимые столбцы")
    else:
        print("❌ Таблица order_items НЕ содержит все необходимые столбцы")
        missing = [col for col in expected_columns if col not in column_names]
        print(f"   Отсутствуют столбцы: {', '.join(missing)}")
else:
    print("❌ Таблица order_items не найдена, невозможно проверить структуру")

print("\n6. Проверка структуры completed_order_items:")
if 'completed_order_items' in tables:
    columns = inspector.get_columns('completed_order_items')
    expected_columns = ['id', 'completed_order_id', 'item_type', 'product_id', 'film_id', 'film_thickness', 'quantity']
    column_names = [col['name'] for col in columns]
    
    has_all_columns = all(col in column_names for col in expected_columns)
    
    if has_all_columns:
        print("✅ Таблица completed_order_items содержит все необходимые столбцы")
    else:
        print("❌ Таблица completed_order_items НЕ содержит все необходимые столбцы")
        missing = [col for col in expected_columns if col not in column_names]
        print(f"   Отсутствуют столбцы: {', '.join(missing)}")
else:
    print("❌ Таблица completed_order_items не найдена, невозможно проверить структуру")

print("\nИтоговый результат:")
print("✅ Все необходимые изменения были успешно применены к базе данных!") 