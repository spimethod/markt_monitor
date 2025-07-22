"""
Главный файл для запуска Polymarket Factory Monitor
Мониторит все фабрики Polymarket на Polygon
"""

import requests
import time
import os
import sys
from loguru import logger

logger.remove()
logger.add(sys.stdout, format="{time} | {level} | {message}", level="INFO")

API_URL = "https://gamma-api.polymarket.com/markets"
SEEN_FILE = "markets_seen.txt"
POLL_INTERVAL = 30  # секунд

# Загружаем уже увиденные рынки из файла
if os.path.exists(SEEN_FILE):
    with open(SEEN_FILE, "r") as f:
        SEEN_MARKETS = set(line.strip() for line in f if line.strip())
else:
    SEEN_MARKETS = set()


def save_seen():
    with open(SEEN_FILE, "w") as f:
        for market_id in SEEN_MARKETS:
            f.write(market_id + "\n")


def monitor_new_markets():
    params = {
        'active': True,
        'limit': 20,
        'order': 'startDate',  # исправлено!
        'ascending': False
    }
    try:
        response = requests.get(API_URL, params=params, timeout=10)
        response.raise_for_status()
        markets = response.json()
        new_found = False
        for market in markets:
            market_id = market.get('id')
            if market_id and market_id not in SEEN_MARKETS:
                SEEN_MARKETS.add(market_id)
                new_found = True
                logger.info(f"🆕 Новый рынок: {market.get('question')}")
                logger.info(f"ID: {market_id}")
                logger.info(f"Slug: {market.get('slug')}")
                logger.info(f"Start Date: {market.get('start_date')}")
                logger.info(f"Active: {market.get('active')}")
                logger.info("---")
        if new_found:
            save_seen()
        else:
            logger.info("Нет новых рынков. Жду...")
    except Exception as e:
        logger.error(f"Ошибка при запросе к Gamma Markets API: {e}")


def main():
    logger.info("=== Запуск Polymarket Gamma Markets Monitor ===")
    while True:
        monitor_new_markets()
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main() 