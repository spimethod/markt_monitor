-- Скрипт для добавления аналитических полей в таблицу markets
-- Выполните этот скрипт в Railway PostgreSQL

-- Добавляем новые поля для аналитических данных
DO $$
BEGIN
    -- Добавляем поле yes_prices
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'markets' AND column_name = 'yes_prices'
    ) THEN
        ALTER TABLE markets ADD COLUMN yes_prices TEXT;
        RAISE NOTICE 'Добавлено поле yes_prices';
    ELSE
        RAISE NOTICE 'Поле yes_prices уже существует';
    END IF;
    
    -- Добавляем поле no_prices
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'markets' AND column_name = 'no_prices'
    ) THEN
        ALTER TABLE markets ADD COLUMN no_prices TEXT;
        RAISE NOTICE 'Добавлено поле no_prices';
    ELSE
        RAISE NOTICE 'Поле no_prices уже существует';
    END IF;
    
    -- Добавляем поле market_exists
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'markets' AND column_name = 'market_exists'
    ) THEN
        ALTER TABLE markets ADD COLUMN market_exists BOOLEAN DEFAULT FALSE;
        RAISE NOTICE 'Добавлено поле market_exists';
    ELSE
        RAISE NOTICE 'Поле market_exists уже существует';
    END IF;
    
    -- Добавляем поле is_boolean
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'markets' AND column_name = 'is_boolean'
    ) THEN
        ALTER TABLE markets ADD COLUMN is_boolean BOOLEAN DEFAULT FALSE;
        RAISE NOTICE 'Добавлено поле is_boolean';
    ELSE
        RAISE NOTICE 'Поле is_boolean уже существует';
    END IF;
    
    -- Добавляем поле yes_percentage
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'markets' AND column_name = 'yes_percentage'
    ) THEN
        ALTER TABLE markets ADD COLUMN yes_percentage DECIMAL(5,2) DEFAULT 0.00;
        RAISE NOTICE 'Добавлено поле yes_percentage';
    ELSE
        RAISE NOTICE 'Поле yes_percentage уже существует';
    END IF;
    
    -- Добавляем поле contract_address
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'markets' AND column_name = 'contract_address'
    ) THEN
        ALTER TABLE markets ADD COLUMN contract_address TEXT;
        RAISE NOTICE 'Добавлено поле contract_address';
    ELSE
        RAISE NOTICE 'Поле contract_address уже существует';
    END IF;
    
    -- Добавляем поле status
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'markets' AND column_name = 'status'
    ) THEN
        ALTER TABLE markets ADD COLUMN status TEXT DEFAULT 'в работе';
        RAISE NOTICE 'Добавлено поле status';
    ELSE
        RAISE NOTICE 'Поле status уже существует';
    END IF;
    
    -- Добавляем поле last_updated
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'markets' AND column_name = 'last_updated'
    ) THEN
        ALTER TABLE markets ADD COLUMN last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        RAISE NOTICE 'Добавлено поле last_updated';
    ELSE
        RAISE NOTICE 'Поле last_updated уже существует';
    END IF;
    
    -- Добавляем поле created_at_analytic
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'markets' AND column_name = 'created_at_analytic'
    ) THEN
        ALTER TABLE markets ADD COLUMN created_at_analytic TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        RAISE NOTICE 'Добавлено поле created_at_analytic';
    ELSE
        RAISE NOTICE 'Поле created_at_analytic уже существует';
    END IF;
    
    -- Добавляем поле volume
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'markets' AND column_name = 'volume'
    ) THEN
        ALTER TABLE markets ADD COLUMN volume TEXT DEFAULT 'New';
        RAISE NOTICE 'Добавлено поле volume';
    ELSE
        RAISE NOTICE 'Поле volume уже существует';
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

-- Показываем статистику по записям
SELECT 
    COUNT(*) as total_markets,
    COUNT(yes_prices) as markets_with_analytics,
    COUNT(*) - COUNT(yes_prices) as markets_without_analytics
FROM markets; 