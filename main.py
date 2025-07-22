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
    accepting_orders BOOLEAN,
    active BOOLEAN,
    slug TEXT
);
"""

INSERT_MARKET_SQL = """
INSERT INTO markets (id, question, created_at, accepting_orders, active, slug)
VALUES %s
ON CONFLICT (id) DO NOTHING;
"""

DELETE_OLD_SQL = """
DELETE FROM markets WHERE created_at IS NOT NULL AND created_at < %s;
"""

RETENTION_HOURS = 25

def get_creation_time(market):
    # Пробуем разные варианты времени создания
    for key in ["startTime", "start_time", "startDate", "start_date", "createdAt", "created_at"]:
        val = market.get(key)
        if val:
            try:
                # Приводим к datetime
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            except Exception:
                pass
    return None

def get_accepting_orders(market):
    return bool(market.get("accepting_orders", False))

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
            get_accepting_orders(m),
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

def monitor_new_markets():
    params = {
        'active': True,
        'limit': 3,
        'order': 'startDate',
        'ascending': False
    }
    try:
        response = requests.get(API_URL, params=params, timeout=10)
        response.raise_for_status()
        markets = response.json()
        new_markets = []
        for market in markets:
            question = get_question(market) or ""
            if question.startswith("Bitcoin Up or Down"):
                continue  # Пропускаем такие рынки
            market_id = get_id(market)
            if not market_exists(market_id):
                new_markets.append(market)
                logger.info(f"🆕 Новый рынок: {question}")
                logger.info(f"ID: {market_id}")
                logger.info(f"Время создания: {get_creation_time(market)}")
                logger.info(f"Можно делать ставки: {get_accepting_orders(market)}")
                logger.info(f"Активный: {get_active(market)}")
                logger.info(f"Slug: {get_slug(market)}")
                logger.info("---")
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