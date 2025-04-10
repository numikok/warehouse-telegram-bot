from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Получение строки подключения к БД
DATABASE_URL = os.getenv("DATABASE_URL")

# Создание подключения к БД
engine = create_engine(DATABASE_URL)

# SQL для изменения enum типа
with engine.connect() as conn:
    # Начало транзакции
    trans = conn.begin()
    try:
        # Создаем временный тип с новым значением
        conn.execute(text("""
        ALTER TYPE userrole ADD VALUE 'NONE' AFTER 'WAREHOUSE';
        """))
        
        # Коммит транзакции
        trans.commit()
        print("Успешно добавлено значение 'NONE' в enum userrole")
    except Exception as e:
        # Если возникла ошибка, откатываем транзакцию
        trans.rollback()
        print(f"Ошибка при добавлении значения 'NONE' в enum userrole: {str(e)}")
        
        # Возможно, значение уже существует, или требуется другой подход
        # Попробуем альтернативный вариант с пересозданием типа
        try:
            trans = conn.begin()
            
            # Создаем временный тип с новым значением
            conn.execute(text("""
            CREATE TYPE userrole_new AS ENUM ('NONE', 'SUPER_ADMIN', 'SALES_MANAGER', 'PRODUCTION', 'WAREHOUSE');
            """))
            
            # Обновляем таблицу users, чтобы использовать новый тип
            conn.execute(text("""
            ALTER TABLE users 
            ALTER COLUMN role TYPE userrole_new 
            USING (role::text::userrole_new);
            """))
            
            # Удаляем старый тип
            conn.execute(text("""
            DROP TYPE userrole;
            """))
            
            # Переименовываем новый тип в старое имя
            conn.execute(text("""
            ALTER TYPE userrole_new RENAME TO userrole;
            """))
            
            # Коммит транзакции
            trans.commit()
            print("Успешно пересоздан enum userrole с добавлением значения 'NONE'")
        except Exception as e2:
            trans.rollback()
            print(f"Ошибка при пересоздании enum userrole: {str(e2)}") 