# 🚀 ФИНАЛЬНЫЕ ПЕРЕМЕННЫЕ ДЛЯ RAILWAY - БОЕВОЙ РЕЖИМ

⚠️ **ВНИМАНИЕ: Эта конфигурация для РЕАЛЬНОЙ торговли с настоящими деньгами!**

## 🔑 ОБЯЗАТЕЛЬНЫЕ ПЕРЕМЕННЫЕ (заполните своими данными)

```bash
PRIVATE_KEY=ваш_приватный_ключ_с_magic_link
POLYMARKET_PROXY_ADDRESS=0x190Cc00825739D2a20DA3036a8D854193429C84E
SIGNATURE_TYPE=1
TELEGRAM_BOT_TOKEN=ваш_токен_бота
TELEGRAM_CHAT_ID=ваш_chat_id
```

## 💾 БАЗА ДАННЫХ (PostgreSQL с автоматическим fallback)

```bash
# Используйте DATABASE_URL от PostgreSQL сервиса Railway
# Если PostgreSQL недоступен, бот автоматически переключится на SQLite
# Для принудительного использования SQLite: DATABASE_URL=sqlite+aiosqlite:///./bot.db
```

## 💰 ТОРГОВЫЕ НАСТРОЙКИ (по вашим требованиям)

```bash
# Основные параметры торговли
POSITION_SIZE_USD=1.0
PROFIT_TARGET_PERCENT=10.0
TRADING_STRATEGY=conservative
POSITION_SIDE=NO
ENVIRONMENT=production

# Фильтры рынков
MIN_LIQUIDITY_USD=100.0
TIME_WINDOW_MINUTES=10
MAX_NO_PRICE=0.85

# Новые настраиваемые лимиты
MAX_OPEN_POSITIONS=10
MAX_POSITION_HOURS=24
STOP_LOSS_PERCENT=-20.0
MAX_POSITION_PERCENT_OF_BALANCE=10.0

# Дневные лимиты сделок
MAX_DAILY_TRADES_CONSERVATIVE=10
MAX_DAILY_TRADES_AGGRESSIVE=25

# Интервалы мониторинга (ускоренные)
POSITION_MONITOR_INTERVAL_SECONDS=10
BALANCE_MONITOR_INTERVAL_SECONDS=60
BALANCE_CHECK_FREQUENCY_SECONDS=30
```

## 📱 УВЕДОМЛЕНИЯ И МОНИТОРИНГ

```bash
NOTIFY_NEW_MARKETS=true
NOTIFY_TRADES=true
NOTIFY_PROFITS=true
NOTIFY_ERRORS=true
DEBUG=false
LOG_LEVEL=INFO
LOG_TO_FILE=true
```

## 🎯 ОСОБЕННОСТИ НОВОЙ КОНФИГУРАЦИИ

### ⚡ **Моментальная покупка + 10-минутное окно:**

- `TIME_WINDOW_MINUTES=10` - окно на покупку после фильтрации
- WebSocket обеспечивает мгновенную реакцию на новые рынки
- После 10 минут бот забивает на позицию

### 🔄 **Параллельная работа:**

- `MAX_OPEN_POSITIONS=10` - до 10 позиций одновременно
- Бот покупает даже при уже открытых позициях
- Каждая позиция обрабатывается независимо

### 📊 **Настраиваемые лимиты через Railway:**

- `PROFIT_TARGET_PERCENT=10.0` - цель прибыли 10%
- `STOP_LOSS_PERCENT=-20.0` - стоп-лосс 20%
- `MAX_POSITION_HOURS=24` - максимум 24 часа держания
- `MAX_POSITION_PERCENT_OF_BALANCE=10.0` - максимум 10% от баланса на позицию
- `MAX_DAILY_TRADES_CONSERVATIVE=10` - лимит сделок для консервативной стратегии
- `MAX_DAILY_TRADES_AGGRESSIVE=25` - лимит сделок для агрессивной стратегии

## ⚙️ КАК ИЗМЕНИТЬ НАСТРОЙКИ В RAILWAY

1. **Зайдите в Railway Dashboard**
2. **Выберите ваш проект**
3. **Variables → Edit**
4. **Измените нужную переменную:**
   - Прибыль: `PROFIT_TARGET_PERCENT=15.0` (15%)
   - Стоп-лосс: `STOP_LOSS_PERCENT=-30.0` (30%)
   - Время держания: `MAX_POSITION_HOURS=48` (48 часов)
   - Лимит позиций: `MAX_OPEN_POSITIONS=5` (5 позиций)
5. **Save** - бот автоматически перезапустится

## 🛡️ БЕЗОПАСНОСТЬ И МОНИТОРИНГ

### 🔐 **Безопасное подключение аккаунта:**

- Используйте отдельный кошелек для бота (рекомендуется)
- Начните с небольшой суммы ($20-50)
- Получите PRIVATE_KEY с https://reveal.magic.link/polymarket

### 📊 **Ускоренный мониторинг:**

- WebSocket: в реальном времени (мгновенно)
- HTTP запросы: каждые 0.1 секунды (настраиваемо)
- Позиции: каждые 10 секунд (ускорено!)
- Балансы: каждую минуту (ускорено!)
- Все интервалы настраиваются через переменные Railway

### 💾 **База данных с автоматическим fallback:**

- PostgreSQL: основная база данных (предпочтительно)
- SQLite fallback: если PostgreSQL недоступен
- Автоматические retry с таймаутами
- Graceful degradation без потери функциональности

## 🎮 TELEGRAM КОМАНДЫ ДЛЯ УПРАВЛЕНИЯ

### 📊 Мониторинг:

- `/status` - статус бота и статистика (включая статус БД)
- `/balance` - баланс и P&L
- `/positions` - открытые позиции

### 🔧 Управление:

- `/stop` - остановить торговлю
- `/start_trading` - запустить торговлю

### ℹ️ Справка:

- `/help` - справка по командам

## 🔥 ГОТОВАЯ СТРОКА ДЛЯ КОПИРОВАНИЯ В RAILWAY

```bash
PRIVATE_KEY=ваш_приватный_ключ_с_magic_link
POLYMARKET_PROXY_ADDRESS=0x190Cc00825739D2a20DA3036a8D854193429C84E
SIGNATURE_TYPE=1
TELEGRAM_BOT_TOKEN=ваш_токен_бота
TELEGRAM_CHAT_ID=ваш_chat_id
POSITION_SIZE_USD=1.0
PROFIT_TARGET_PERCENT=10.0
TRADING_STRATEGY=conservative
POSITION_SIDE=NO
MIN_LIQUIDITY_USD=100.0
TIME_WINDOW_MINUTES=10
MAX_NO_PRICE=0.85
MAX_OPEN_POSITIONS=10
MAX_POSITION_HOURS=24
STOP_LOSS_PERCENT=-20.0
MAX_POSITION_PERCENT_OF_BALANCE=10.0
MAX_DAILY_TRADES_CONSERVATIVE=10
MAX_DAILY_TRADES_AGGRESSIVE=25
POSITION_MONITOR_INTERVAL_SECONDS=10
BALANCE_MONITOR_INTERVAL_SECONDS=60
BALANCE_CHECK_FREQUENCY_SECONDS=30
NOTIFY_NEW_MARKETS=true
NOTIFY_TRADES=true
NOTIFY_PROFITS=true
NOTIFY_ERRORS=true
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
LOG_TO_FILE=true
```

## ✅ ПРОВЕРЬТЕ ПЕРЕД ЗАПУСКОМ

- [ ] PRIVATE_KEY получен и вставлен
- [ ] TELEGRAM_BOT_TOKEN от @BotFather
- [ ] TELEGRAM_CHAT_ID от @userinfobot
- [ ] POLYMARKET_PROXY_ADDRESS исправлен (42 символа)
- [ ] Баланс пополнен ($20+ для начала)
- [ ] Все переменные скопированы в Railway
- [ ] Настройки риска устраивают

## 🔧 ИСПРАВЛЕНИЯ В ЭТОЙ ВЕРСИИ

### ✅ **Исправлена проблема с PostgreSQL:**

- Добавлены таймауты подключения (15 секунд)
- Retry механизм (3 попытки с exponential backoff)
- Автоматический fallback на SQLite если PostgreSQL недоступен
- Команда `/status` показывает статус базы данных

### ✅ **Быстрая инициализация:**

- Максимум 15 секунд ожидания PostgreSQL
- Немедленный переход на SQLite при проблемах
- Логирование всех попыток подключения

🚀 **После добавления переменных бот запустится быстро независимо от статуса PostgreSQL!**
