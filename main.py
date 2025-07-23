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

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS markets (
    id TEXT PRIMARY KEY,
    question TEXT,
    created_at TIMESTAMP,
    active BOOLEAN,
    slug TEXT
);
"""

INSERT_MARKET_SQL = """
INSERT INTO markets (id, question, created_at, active, slug)
VALUES %s
ON CONFLICT (id) DO NOTHING;
"""

DELETE_OLD_SQL = """
DELETE FROM markets WHERE created_at IS NOT NULL AND created_at < %s;
"""

RETENTION_HOURS = 25

def get_creation_time(market):
    for key in ["startTime", "start_time", "startDate", "start_date", "createdAt", "created_at"]:
        val = market.get(key)
        if val:
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            except Exception:
                pass
    return None

def get_active(market):
    return bool(market.get("active", False))

def get_slug(market):
    return market.get("slug")

def get_question(market):
    return market.get("question")

def get_id(market):
    return str(market.get("id"))

def connect_db():
    return psycopg2.connect(
        host=PGHOST,
        port=PGPORT,
        user=PGUSER,
        password=PGPASSWORD,
        dbname=PGDATABASE
    )

def ensure_table():
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
        conn.commit()

def market_exists(market_id):
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM markets WHERE id = %s", (market_id,))
            return cur.fetchone() is not None

def save_markets(markets):
    values = []
    for m in markets:
        values.append((
            get_id(m),
            get_question(m),
            get_creation_time(m),
            get_active(m),
            get_slug(m)
        ))
    if not values:
        return
    with connect_db() as conn:
        with conn.cursor() as cur:
            execute_values(cur, INSERT_MARKET_SQL, values)
        conn.commit()

def delete_old_markets():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RETENTION_HOURS)
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(DELETE_OLD_SQL, (cutoff,))
        conn.commit()
    logger.info(f"Удалены рынки старше {RETENTION_HOURS} часов")

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
            if not market_exists(market_id):
                new_markets.append(market)
                created_at = get_creation_time(market)
                
                # Логируем новый рынок
                logger.info(f"🆕 Новый рынок: {question}")
                logger.info(f"ID: {market_id}")
                logger.info(f"Время создания: {created_at}")
                logger.info(f"Активный: {get_active(market)}")
                logger.info(f"Slug: {get_slug(market)}")
                logger.info("---")
                
                # Отправляем уведомление в Telegram
                message = (
                    f"🆕 <b>Новый рынок на Polymarket!</b>\n\n"
                    f"📋 Вопрос: {question}\n"
                    f"🆔 ID: {market_id}\n"
                    f"⏰ Создан: {created_at}\n"
                    f"🔗 Slug: {get_slug(market)}\n"
                    f"📊 Активен: {'Да' if get_active(market) else 'Нет'}"
                )
                send_telegram_message(message)
            else:
                already_exists += 1
        
        logger.info(f"📈 Статистика: {len(new_markets)} новых, {already_exists} уже в базе, {skipped_special} пропущено (Up or Down)")
        
        if new_markets:
            save_markets(new_markets)
        else:
            logger.info("Нет новых рынков. Жду...")
    except Exception as e:
        logger.error(f"Ошибка при запросе к Gamma Markets API: {e}")

def main():
    logger.info("=== Запуск Polymarket Gamma Markets Monitor (Postgres) ===")
    ensure_table()
    while True:
        monitor_new_markets()
        delete_old_markets()
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main() 