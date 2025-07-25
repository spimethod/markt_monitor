-- Скрипт для упрощения структуры таблицы markets
-- Выполните этот скрипт в Railway PostgreSQL

-- Создаем новую упрощенную таблицу
CREATE TABLE IF NOT EXISTS markets_simple (
    id INTEGER PRIMARY KEY,
    question TEXT,
    created_at TIMESTAMP,
    active BOOLEAN,
    enable_order_book BOOLEAN,
    slug TEXT UNIQUE -- Добавляем поле slug
);

-- Копируем данные из старой таблицы (только нужные поля)
INSERT INTO markets_simple (id, question, created_at, active, enable_order_book, slug)
SELECT 
    id,
    question,
    created_at,
    active,
    enable_order_book,
    slug -- Копируем slug
FROM markets
WHERE enable_order_book IS NOT NULL AND slug IS NOT NULL; -- Убедимся, что slug не NULL

-- Удаляем старую таблицу
DROP TABLE IF EXISTS markets;

-- Переименовываем новую таблицу
ALTER TABLE markets_simple RENAME TO markets;

-- Добавляем UNIQUE ограничение на slug, если его нет (на случай, если таблица уже существовала без него)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'markets'::regclass AND contype = 'u' AND conname = 'markets_slug_key'
    ) THEN
        ALTER TABLE markets ADD CONSTRAINT markets_slug_key UNIQUE (slug);
        RAISE NOTICE 'Добавлено UNIQUE ограничение на slug';
    ELSE
        RAISE NOTICE 'UNIQUE ограничение на slug уже существует';
    END IF;
END $$;

-- Проверяем результат
SELECT 
    column_name, 
    data_type, 
    is_nullable, 
    column_default 
FROM 
    information_schema.columns 
WHERE 
    table_name = 'markets' 
ORDER BY 
    ordinal_position;

-- Показываем количество записей
SELECT COUNT(*) FROM markets;

-- Показываем последние записи
SELECT * FROM markets ORDER BY created_at DESC LIMIT 5; 