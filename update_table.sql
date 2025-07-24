-- Скрипт для обновления структуры таблицы markets
-- Выполните этот скрипт в Railway PostgreSQL

-- Добавляем поле market_status, если его нет
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'markets' AND column_name = 'market_status'
    ) THEN
        ALTER TABLE markets ADD COLUMN market_status TEXT DEFAULT 'created';
        RAISE NOTICE 'Добавлено поле market_status';
    ELSE
        RAISE NOTICE 'Поле market_status уже существует';
    END IF;
END $$;

-- Добавляем поле trading_activated_at, если его нет
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'markets' AND column_name = 'trading_activated_at'
    ) THEN
        ALTER TABLE markets ADD COLUMN trading_activated_at TIMESTAMP NULL;
        RAISE NOTICE 'Добавлено поле trading_activated_at';
    ELSE
        RAISE NOTICE 'Поле trading_activated_at уже существует';
    END IF;
END $$;

-- Показываем текущую структуру таблицы
SELECT 
    column_name, 
    data_type, 
    is_nullable, 
    column_default
FROM information_schema.columns 
WHERE table_name = 'markets'
ORDER BY ordinal_position;

-- Показываем статистику по статусам
SELECT 
    market_status, 
    COUNT(*) as count 
FROM markets 
GROUP BY market_status 
ORDER BY count DESC;

-- Показываем последние записи
SELECT 
    id, 
    slug, 
    market_status, 
    created_at, 
    trading_activated_at
FROM markets 
ORDER BY created_at DESC 
LIMIT 5; 