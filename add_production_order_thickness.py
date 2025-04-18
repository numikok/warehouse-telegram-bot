import os
import psycopg2
from urllib.parse import urlparse

# Получаем URL базы данных из переменной окружения
DATABASE_URL = os.environ.get('DATABASE_URL')

# Подключаемся к базе данных
if DATABASE_URL:
    # Heroku использует префикс postgres://, но psycopg2 требует postgresql://
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://')
    
    # Парсим URL для получения параметров подключения
    url = urlparse(DATABASE_URL)
    
    # Подключаемся к базе данных
    conn = psycopg2.connect(
        host=url.hostname,
        database=url.path[1:],
        user=url.username,
        password=url.password,
        port=url.port
    )
    
    # Открываем курсор
    cursor = conn.cursor()
    
    try:
        # Проверяем, существует ли уже столбец panel_thickness
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='production_orders' AND column_name='panel_thickness'
        """)
        
        # Если cursor.fetchone() возвращает None, значит столбец не существует
        if cursor.fetchone() is None:
            # Добавляем столбец panel_thickness
            cursor.execute("""
                ALTER TABLE production_orders 
                ADD COLUMN panel_thickness FLOAT NOT NULL DEFAULT 0.5
            """)
            print("Столбец panel_thickness успешно добавлен в таблицу production_orders")
        else:
            print("Столбец panel_thickness уже существует в таблице production_orders")
        
        # Фиксируем изменения
        conn.commit()
    except Exception as e:
        print(f"Ошибка при добавлении столбца: {e}")
        conn.rollback()
    finally:
        # Закрываем курсор и соединение
        cursor.close()
        conn.close()
else:
    print("DATABASE_URL не найден. Невозможно подключиться к базе данных.") 