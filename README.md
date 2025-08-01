# Markt Monitor

Мониторинг всех фабрик Polymarket на Polygon в реальном времени.

## 🎯 Что делает

Этот бот отслеживает создание новых рынков на всех фабриках Polymarket:

- **AMM v1** - Автоматические маркет-мейкеры (версия 1)
- **CLOB** - Central Limit Order Book
- **AMM v2** - Автоматические маркет-мейкеры (версия 2)
- **Parlay** - Парлай рынки

## 🚀 Быстрый старт

### Локальный запуск

```bash
# Клонирование
git clone https://github.com/spimethod/markt_monitor.git
cd markt_monitor

# Установка зависимостей
pip install -r requirements.txt

# Запуск
python main.py
```

### Развертывание на Railway

1. **Форкните репозиторий** на GitHub
2. **Создайте проект** на [railway.app](https://railway.app)
3. **Подключите GitHub репозиторий**
4. **Деплой запустится автоматически**

## 📡 Мониторинг

Бот подключается к Polygon через WebSocket и отслеживает события:

- `MarketCreated` - создание AMM рынков
- `OrderbookCreated` - создание CLOB ордербуков
- `ParlayCreated` - создание парлай рынков

### Пример вывода

```
=== Запуск Polymarket Factory Monitor ===
Подключение к Polygon WebSocket...
✅ Подключение к Polygon установлено
✅ Фильтр событий создан
📡 Мониторинг фабрик: 4 адресов
🟢 Начинаю мониторинг новых рынков...

🆕 CLOB orderbook 0x1234...abcd | creator 0xefgh...5678
🆕 AMM market    0xabcd...1234
🆕 Parlay        0x5678...efgh | creator 0x1234...abcd
```

## ⚙️ Конфигурация

### WebSocket RPC

По умолчанию используется Alchemy WebSocket:

```
wss://polygon-mainnet.g.alchemy.com/v2/fqlDOKopXL8QsZnEdCrkV
```

### Фабрики Polymarket

Мониторятся следующие адреса:

- `0x8B9805A2f595B6705e74F7310829f2d299D21522` - FP-MM v1
- `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E` - CLOB factory
- `0x7bB0f881F37331d77b58dcDFdB9a46f0BfA4eF4F` - FP-MM v2
- `0xa9425A42E0B664F8B4F4B5f4b8224F7C7F3B3CdF` - Parlay factory

## 🔧 Технические детали

### Зависимости

- `web3==7.12.1` - для работы с блокчейном
- `loguru>=0.7.0` - для логирования
- `eth-utils>=2.0.0` - утилиты для Ethereum

### Архитектура

- **Синхронный WebSocket** - использует `LegacyWebSocketProvider`
- **Фильтр событий** - подписка на события от всех фабрик
- **Graceful shutdown** - корректная остановка при сигналах

## 📊 Логирование

Бот использует `loguru` для структурированного логирования:

- `INFO` - подключение и события
- `ERROR` - ошибки подключения и обработки
- `WARNING` - предупреждения

## 🛡️ Безопасность

- **Только мониторинг** - бот не совершает транзакции
- **Read-only доступ** - только чтение событий из блокчейна
- **Без приватных ключей** - не требует настройки кошелька

## 🐛 Устранение неполадок

### Проблема: "Не удалось подключиться к Polygon WS RPC"

**Решение:** Проверьте доступность WebSocket URL и интернет-соединение

### Проблема: "Нет новых событий"

**Решение:** Это нормально - рынки создаются нерегулярно. Бот работает корректно.

### Проблема: "Ошибка обработки события"

**Решение:** Проверьте логи - возможно, изменился формат событий

## 📈 Возможности расширения

- **Telegram уведомления** - отправка событий в чат
- **База данных** - сохранение событий в SQLite/PostgreSQL
- **API endpoint** - REST API для получения статистики
- **Веб-интерфейс** - дашборд для мониторинга

## 🤝 Вклад в проект

1. Форкните репозиторий
2. Создайте ветку для новой функции
3. Внесите изменения
4. Создайте Pull Request

## 📄 Лицензия

MIT License - см. файл LICENSE

## 📞 Поддержка

- 📖 [Документация Polymarket](https://docs.polymarket.com/)
- 💬 [GitHub Issues](https://github.com/spimethod/markt_monitor/issues)
- 🐦 [Telegram](https://t.me/polymarket_support)

---

⭐ **Нравится проект?** Поставьте звездочку на GitHub!
