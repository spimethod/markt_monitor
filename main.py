"""
Главный файл для запуска Polymarket Factory Monitor
Мониторит все фабрики Polymarket на Polygon
"""

import requests
import time
import os
import sys
import psycopg2
from psycopg2.extras import execute_values
from loguru import logger
from datetime import datetime, timedelta, timezone

# === Конфиг ===
API_URL = os.getenv("API_URL")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 30))  # секунд

# === Telegram конфиг ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === Параметры подключения к PostgreSQL (Railway) ===
PGHOST = os.getenv("PGHOST")
PGPORT = os.getenv("PGPORT", "5432")
PGUSER = os.getenv("PGUSER")
PGPASSWORD = os.getenv("PGPASSWORD")
PGDATABASE = os.getenv("PGDATABASE")

logger.remove()
logger.add(sys.stdout, format="{time} | {level} | {message}", level="INFO")

def send_telegram_message(message):
    """Отправляет сообщение в Telegram, если настроены токен и чат."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=data, timeout=10)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Ошибка отправки в Telegram: {e}")

def connect_db():
    """Подключение к PostgreSQL"""
    try:
        conn = psycopg2.connect(
            host=PGHOST,
            port=PGPORT,
            user=PGUSER,
            password=PGPASSWORD,
            database=PGDATABASE
        )
        return conn
    except Exception as e:
        logger.error(f"Ошибка подключения к БД: {e}")
        return None

# === SQL схемы ===
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS markets (
    id INTEGER PRIMARY KEY,
    question TEXT,
    created_at TIMESTAMP,
    active BOOLEAN,
    enable_order_book BOOLEAN
);
"""

INSERT_MARKET_SQL = """
INSERT INTO markets (id, question, created_at, active, enable_order_book)
VALUES %s
ON CONFLICT (id) DO NOTHING;
"""

def ensure_table():
    """Создает таблицу, если она не существует"""
    conn = connect_db()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(CREATE_TABLE_SQL)
        conn.commit()
        logger.info("✅ Таблица markets готова")
        return True
    except Exception as e:
        logger.error(f"Ошибка создания таблицы: {e}")
        return False
    finally:
        conn.close()

def market_exists(market_id):
    """Проверяет, существует ли рынок в БД"""
    conn = connect_db()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM markets WHERE id = %s", (market_id,))
            exists = cursor.fetchone() is not None
            if exists:
                logger.debug(f"Рынок {market_id} уже существует в БД")
            return exists
    except Exception as e:
        logger.error(f"Ошибка проверки существования рынка: {e}")
        return False
    finally:
        conn.close()

def save_markets(markets):
    """Сохраняет новые рынки в БД"""
    conn = connect_db()
    if not conn:
        return
    
    try:
        with conn.cursor() as cursor:
            # Подготавливаем данные для вставки
            market_data = []
            for market in markets:
                market_data.append((
                    get_id(market),
                    get_question(market),
                    get_creation_time(market),
                    get_active(market),
                    get_enable_order_book(market)
                ))
            
            # Вставляем данные
            execute_values(cursor, INSERT_MARKET_SQL, market_data)
            conn.commit()
            logger.info(f"💾 Сохранено {len(markets)} новых рынков")
    except Exception as e:
        logger.error(f"Ошибка сохранения рынков: {e}")
    finally:
        conn.close()

def delete_old_markets():
    """Удаляет рынки старше RETENTION_HOURS часов"""
    RETENTION_HOURS = 25
    conn = connect_db()
    if not conn:
        return
    
    try:
        with conn.cursor() as cursor:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=RETENTION_HOURS)
            cursor.execute(
                "DELETE FROM markets WHERE created_at < %s",
                (cutoff_time,)
            )
            deleted_count = cursor.rowcount
            conn.commit()
            if deleted_count > 0:
                logger.info(f"🗑️ Удалено {deleted_count} старых рынков")
    except Exception as e:
        logger.error(f"Ошибка удаления старых рынков: {e}")
    finally:
        conn.close()

# === Функции извлечения данных из API ===
def get_id(market):
    """Извлекает ID рынка"""
    return market.get('id')

def get_question(market):
    """Извлекает вопрос рынка"""
    return market.get('question')

def get_creation_time(market):
    """Извлекает время создания рынка"""
    # Пробуем разные поля для времени создания
    time_fields = ['created_at', 'createdAt', 'start_date', 'startDate', 'created']
    for field in time_fields:
        if field in market and market[field]:
            try:
                # Если это строка, парсим её
                if isinstance(market[field], str):
                    dt = datetime.fromisoformat(market[field].replace('Z', '+00:00'))
                    # Убеждаемся, что у datetime есть timezone
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                # Если это timestamp
                elif isinstance(market[field], (int, float)):
                    return datetime.fromtimestamp(market[field], tz=timezone.utc)
            except:
                continue
    
    # Если ничего не найдено, возвращаем текущее время
    return datetime.now(timezone.utc)

def get_active(market):
    """Извлекает статус активности"""
    return market.get('active', False)

def get_enable_order_book(market):
    """Извлекает enable_order_book"""
    return market.get('enableOrderBook', False)

def monitor_new_markets():
    params = {
        'active': True,
        'limit': 3,
        'order': 'startDate',
        'ascending': False
    }
    SKIP_PREFIXES = [
        "Bitcoin Up or Down",
        "Ethereum Up or Down",
        "Solana Up or Down",
        "XRP Up or Down"
    ]
    try:
        response = requests.get(API_URL, params=params, timeout=10)
        response.raise_for_status()
        markets = response.json()
        logger.info(f"📊 Получено от API: {len(markets)} рынков")
        
        new_markets = []
        skipped_special = 0
        already_exists = 0
        
        for market in markets:
            question = get_question(market) or ""
            if any(question.startswith(prefix) for prefix in SKIP_PREFIXES):
                skipped_special += 1
                continue  # Пропускаем такие рынки
            
            market_id = get_id(market)
            
            # Проверяем существование в БД
            if market_exists(market_id):
                already_exists += 1
                logger.debug(f"Рынок {market_id} уже существует в БД, пропускаю")
                continue
            
            logger.info(f"🆕 Обрабатываю новый рынок: {market_id}")
            
            new_markets.append(market)
            created_at = get_creation_time(market)
            
            # Логируем новый рынок
            logger.info(f"🆕 Новый рынок: {question}")
            logger.info(f"ID: {market_id}")
            logger.info(f"Время создания: {created_at}")
            logger.info(f"Активный: {get_active(market)}")
            logger.info(f"Enable Order Book: {get_enable_order_book(market)}")
            logger.info("---")
            
            # Отправляем уведомление в Telegram
            message = (
                f"🆕 <b>Новый рынок на Polymarket!</b>\n\n"
                f"📋 Вопрос: {question}\n"
                f"🆔 ID: {market_id}\n"
                f"⏰ Создан: {created_at}\n"
                f"📊 Активен: {'Да' if get_active(market) else 'Нет'}\n"
                f"📚 Order Book: {'Да' if get_enable_order_book(market) else 'Нет'}"
            )
            send_telegram_message(message)
        
        logger.info(f"📈 Статистика: {len(new_markets)} новых, {already_exists} уже в базе, {skipped_special} пропущено (Up or Down)")
        
        if new_markets:
            save_markets(new_markets)
        else:
            logger.info("Нет новых рынков. Жду...")
    except Exception as e:
        logger.error(f"Ошибка при запросе к Gamma Markets API: {e}")

def main():
    logger.info("=== Запуск Polymarket Market Monitor ===")
    
    # Проверяем подключение к БД
    if not ensure_table():
        logger.error("❌ Не удалось подключиться к базе данных")
        return
    
    logger.info("🟢 Начинаю мониторинг новых рынков...")
    
    while True:
        try:
            # Мониторинг новых рынков
            monitor_new_markets()
            
            # Очищаем старые записи
            delete_old_markets()
            
            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            logger.info("⏹️ Остановка Polymarket Market Monitor...")
            break
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
            time.sleep(30)  # Ждем перед повторной попыткой
    
    logger.info("=== Polymarket Market Monitor остановлен ===")

if __name__ == "__main__":
    main() 