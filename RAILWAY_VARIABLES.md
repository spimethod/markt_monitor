# 🚀 Переменные окружения для Railway - ПРОДАКШН РЕЖИМ

⚠️ **ВНИМАНИЕ: Эта конфигурация для РЕАЛЬНОЙ торговли с настоящими деньгами!**

## 🔑 ОБЯЗАТЕЛЬНЫЕ ПЕРЕМЕННЫЕ

Эти переменные необходимо заполнить для работы бота:

```
PRIVATE_KEY=0x...
POLYMARKET_PROXY_ADDRESS=0x190Cc00825739D2a20DA3036a8D85419342C84E
SIGNATURE_TYPE=1
TELEGRAM_BOT_TOKEN=123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
TELEGRAM_CHAT_ID=123456789
```

## 💰 ТОРГОВЫЕ НАСТРОЙКИ (продакшн с $1 позициями)

```
POSITION_SIZE_USD=1.0
PROFIT_TARGET_PERCENT=10.0
TRADING_STRATEGY=conservative
POSITION_SIDE=NO
MIN_LIQUIDITY_USD=100.0
TIME_WINDOW_MINUTES=10
MAX_NO_PRICE=0.85
MAX_OPEN_POSITIONS=2
MAX_POSITION_HOURS=24
STOP_LOSS_PERCENT=-20.0
MAX_POSITION_PERCENT_OF_BALANCE=5.0
```

## 📱 УВЕДОМЛЕНИЯ TELEGRAM

```
NOTIFY_NEW_MARKETS=true
NOTIFY_TRADES=true
NOTIFY_PROFITS=true
NOTIFY_ERRORS=true
```

## ⚙️ ПРОДАКШН НАСТРОЙКИ

```
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
LOG_TO_FILE=true
LOG_FILE_PATH=logs/bot.log
TIMEZONE=UTC
API_ROTATION_ENABLED=true
REQUEST_DELAY_SECONDS=0.1
```

## 📋 ГОТОВЫЙ СПИСОК ДЛЯ КОПИРОВАНИЯ В RAILWAY

```bash
PRIVATE_KEY=ваш_приватный_ключ_с_magic_link
POLYMARKET_PROXY_ADDRESS=0x190Cc00825739D2a20DA3036a8D85419342C84E
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
MAX_OPEN_POSITIONS=2
MAX_POSITION_HOURS=24
STOP_LOSS_PERCENT=-20.0
MAX_POSITION_PERCENT_OF_BALANCE=5.0
NOTIFY_NEW_MARKETS=true
NOTIFY_TRADES=true
NOTIFY_PROFITS=true
NOTIFY_ERRORS=true
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
LOG_TO_FILE=true
LOG_FILE_PATH=logs/bot.log
TIMEZONE=UTC
API_ROTATION_ENABLED=true
REQUEST_DELAY_SECONDS=0.1
```

## 🎯 ОСОБЕННОСТИ ПРОДАКШН КОНФИГУРАЦИИ

### 💰 Безопасные настройки для $1 позиций:

- `POSITION_SIZE_USD=1.0` - по $1 на сделку
- `MAX_OPEN_POSITIONS=2` - максимум 2 позиции
- `MAX_POSITION_PERCENT_OF_BALANCE=5.0` - максимум 5% от баланса

### 🛡️ Защитные механизмы:

- `STOP_LOSS_PERCENT=-20.0` - стоп-лосс 20%
- `TRADING_STRATEGY=conservative` - осторожная стратегия
- `MIN_LIQUIDITY_USD=100.0` - торговля только на ликвидных рынках

### 📊 Мониторинг:

- Все уведомления включены
- Подробные логи для анализа
- Реальная статистика торговли

## ⚠️ ВАЖНЫЕ МОМЕНТЫ

### 🔥 Реальный режим означает:

- ✅ **Реальные ордера** - деньги списываются с баланса
- ✅ **Реальная прибыль/убытки** - можете заработать или потерять
- ✅ **Реальные комиссии** - Polymarket берет комиссии
- ✅ **Реальные балансы** - показывает ваши настоящие USDC

### 🛡️ Меры безопасности:

- Начинайте с **минимального баланса** ($20-50)
- **Следите за уведомлениями** в Telegram
- **Анализируйте логи** каждый день
- **Будьте готовы остановить** бота командой `/stop`

### 📈 Ожидаемые результаты:

- При балансе $20 и позициях $1 = 20 возможных сделок
- При успешности 60% и прибыли 10% = +$1.20 с 20 сделок
- Реальная доходность зависит от рынка

## 🚀 ПЛАН ЗАПУСКА

1. **Пополните баланс** минимум $20 USDC на Polymarket
2. **Добавьте переменные** в Railway Dashboard
3. **Запустите бота** и сразу проверьте `/status`
4. **Следите за первыми сделками** через Telegram
5. **Анализируйте результаты** через неделю

## 📞 Команды для мониторинга:

- `/status` - статус и статистика
- `/balance` - реальный баланс USDC
- `/positions` - открытые позиции
- `/stop` - остановить торговлю
- `/start_trading` - возобновить торговлю

---

⚠️ **ФИНАЛЬНОЕ ПРЕДУПРЕЖДЕНИЕ**: Вы переходите в режим реальной торговли. Все операции будут выполняться с настоящими деньгами. Убедитесь, что понимаете риски!
