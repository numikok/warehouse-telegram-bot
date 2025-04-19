-- Проверяем и удаляем таблицу order_films, если она существует
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'order_films'
    ) THEN
        DROP TABLE "order_films";
        RAISE NOTICE 'Таблица order_films удалена';
    ELSE
        RAISE NOTICE 'Таблица order_films не существует';
    END IF;
END $$;

-- Проверяем и удаляем таблицу completed_order_films, если она существует
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'completed_order_films'
    ) THEN
        DROP TABLE "completed_order_films";
        RAISE NOTICE 'Таблица completed_order_films удалена';
    ELSE
        RAISE NOTICE 'Таблица completed_order_films не существует';
    END IF;
END $$;

-- Проверяем и удаляем таблицу order_products, если она существует
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'order_products'
    ) THEN
        DROP TABLE "order_products";
        RAISE NOTICE 'Таблица order_products удалена';
    ELSE
        RAISE NOTICE 'Таблица order_products не существует';
    END IF;
END $$;

-- Проверяем наличие столбца joint_thickness в таблице order_joints
-- Если его нет, добавляем
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'order_joints'
        AND column_name = 'joint_thickness'
    ) THEN
        ALTER TABLE "order_joints" ADD COLUMN "joint_thickness" FLOAT NOT NULL DEFAULT 0.5;
        RAISE NOTICE 'Столбец joint_thickness добавлен в таблицу order_joints';
    ELSE
        RAISE NOTICE 'Столбец joint_thickness уже существует в таблице order_joints';
    END IF;
END $$;

-- Проверяем наличие столбца joint_thickness в таблице completed_order_joints
-- Если его нет, добавляем
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'completed_order_joints'
        AND column_name = 'joint_thickness'
    ) THEN
        ALTER TABLE "completed_order_joints" ADD COLUMN "joint_thickness" FLOAT NOT NULL DEFAULT 0.5;
        RAISE NOTICE 'Столбец joint_thickness добавлен в таблицу completed_order_joints';
    ELSE
        RAISE NOTICE 'Столбец joint_thickness уже существует в таблице completed_order_joints';
    END IF;
END $$;

-- Проверяем наличие столбца is_finished в таблице order_items
-- Если он есть, удаляем
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'order_items'
        AND column_name = 'is_finished'
    ) THEN
        ALTER TABLE "order_items" DROP COLUMN "is_finished";
        RAISE NOTICE 'Столбец is_finished удален из таблицы order_items';
    ELSE
        RAISE NOTICE 'Столбец is_finished не существует в таблице order_items';
    END IF;
END $$;

-- Проверяем наличие столбца glue_id в таблице order_glues
-- Если он есть, удаляем
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'order_glues'
        AND column_name = 'glue_id'
    ) THEN
        ALTER TABLE "order_glues" DROP COLUMN "glue_id";
        RAISE NOTICE 'Столбец glue_id удален из таблицы order_glues';
    ELSE
        RAISE NOTICE 'Столбец glue_id не существует в таблице order_glues';
    END IF;
END $$;

-- Проверяем наличие столбца glue_id в таблице completed_order_glues
-- Если он есть, удаляем
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'completed_order_glues'
        AND column_name = 'glue_id'
    ) THEN
        ALTER TABLE "completed_order_glues" DROP COLUMN "glue_id";
        RAISE NOTICE 'Столбец glue_id удален из таблицы completed_order_glues';
    ELSE
        RAISE NOTICE 'Столбец glue_id не существует в таблице completed_order_glues';
    END IF;
END $$; 