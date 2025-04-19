import os
from sqlalchemy import create_engine, inspect, text

# Connect to database
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
inspector = inspect(engine)

def print_table_structure(table_name, expected_columns):
    """Проверить структуру таблицы и вывести результат"""
    print(f"\n=== Проверка таблицы {table_name} ===")
    
    if table_name not in inspector.get_table_names():
        print(f"❌ Таблица {table_name} не существует!")
        return False
    
    columns = inspector.get_columns(table_name)
    column_names = [col["name"] for col in columns]
    
    print(f"Столбцы таблицы {table_name}:")
    for col in columns:
        print(f"- {col['name']}: {col['type']}")
    
    missing = [col for col in expected_columns if col not in column_names]
    extra = [col for col in column_names if col not in expected_columns and col != 'id']
    
    if missing:
        print(f"❌ Отсутствуют столбцы: {', '.join(missing)}")
    
    if extra:
        print(f"❌ Лишние столбцы: {', '.join(extra)}")
    
    if not missing and not extra:
        print(f"✅ Таблица {table_name} соответствует требованиям")
        return True
    return False

# Проверка структуры всех таблиц
print("=== ПРОВЕРКА СТРУКТУРЫ БАЗЫ ДАННЫХ ===")

# 1. Проверка таблицы orders
expected_orders_columns = ["id", "manager_id", "customer_phone", "delivery_address", 
                          "installation_required", "status", "created_at", "updated_at", "completed_at"]
orders_ok = print_table_structure("orders", expected_orders_columns)

# 2. Проверка таблицы order_items
expected_order_items_columns = ["id", "order_id", "color", "thickness", "quantity"]
order_items_ok = print_table_structure("order_items", expected_order_items_columns)

# 3. Проверка таблицы order_joints
expected_order_joints_columns = ["id", "order_id", "joint_type", "joint_color", "joint_thickness", "joint_quantity"]
order_joints_ok = print_table_structure("order_joints", expected_order_joints_columns)

# 4. Проверка таблицы order_glues
expected_order_glues_columns = ["id", "order_id", "quantity"]
order_glues_ok = print_table_structure("order_glues", expected_order_glues_columns)

# Итоговый результат
print("\n=== ИТОГОВЫЙ РЕЗУЛЬТАТ ===")
if orders_ok and order_items_ok and order_joints_ok and order_glues_ok:
    print("✅ Все таблицы соответствуют требуемой структуре")
else:
    print("❌ Некоторые таблицы не соответствуют требуемой структуре") 