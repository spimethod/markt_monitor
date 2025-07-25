-- Скрипт для упрощения структуры таблицы markets
-- Выполните этот скрипт в Railway PostgreSQL

-- Создаем новую упрощенную таблицу
CREATE TABLE IF NOT EXISTS markets_simple (
    id INTEGER PRIMARY KEY,
    question TEXT,
    created_at TIMESTAMP,
    active BOOLEAN,
    enable_order_book BOOLEAN
);

-- Копируем данные из старой таблицы (только нужные поля)
INSERT INTO markets_simple (id, question, created_at, active, enable_order_book)
SELECT 
    id,
    question,
    created_at,
    active,
    enable_order_book
FROM markets
WHERE enable_order_book IS NOT NULL;

-- Удаляем старую таблицу
DROP TABLE IF EXISTS markets;

-- Переименовываем новую таблицу
ALTER TABLE markets_simple RENAME TO markets;

-- Проверяем результат
SELECT 
    column_name, 
    data_type, 
    is_nullable, 
    column_default
FROM information_schema.columns 
WHERE table_name = 'markets'
ORDER BY ordinal_position;

-- Показываем количество записей
SELECT COUNT(*) FROM markets;

-- Показываем последние записи
SELECT * FROM markets ORDER BY created_at DESC LIMIT 5; 