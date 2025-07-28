import os
import time
import logging
import requests
from datetime import datetime, timezone
from loguru import logger
import psycopg2
from psycopg2.extras import execute_values

# Конфигурация
DATABASE_URL = os.getenv("DATABASE_URL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def connect_db():
    """Подключается к PostgreSQL базе данных"""
    try:
        if DATABASE_URL:
            conn = psycopg2.connect(DATABASE_URL)
        else:
            conn = psycopg2.connect(
                host=os.getenv("PGHOST"),
                port=os.getenv("PGPORT", "5432"),
                user=os.getenv("PGUSER"),
                password=os.getenv("PGPASSWORD"),
                database=os.getenv("PGDATABASE")
            )
        return conn
    except Exception as e:
        logger.error(f"Ошибка подключения к БД: {e}")
        return None

def send_telegram_message(message):
    """Отправляет сообщение в Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram не настроен")
        return
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Ошибка отправки в Telegram: {e}")

def get_markets_for_analysis():
    """Получает рынки для анализа (без аналитических данных)"""
    conn = connect_db()
    if not conn:
        return []
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, question, slug, created_at 
                FROM markets 
                WHERE yes_prices IS NULL OR yes_prices = ''
                ORDER BY created_at DESC
                LIMIT 5
            """)
            markets = cursor.fetchall()
            return [
                {
                    'id': row[0],
                    'question': row[1],
                    'slug': row[2],
                    'created_at': row[3]
                }
                for row in markets
            ]
    except Exception as e:
        logger.error(f"Ошибка получения рынков для анализа: {e}")
        return []
    finally:
        conn.close()

def update_market_analytics(market_id, analytics_data):
    """Обновляет аналитические данные рынка"""
    conn = connect_db()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE markets 
                SET yes_prices = %s,
                    no_prices = %s,
                    market_exists = %s,
                    is_boolean = %s,
                    yes_percentage = %s,
                    contract_address = %s,
                    status = %s,
                    last_updated = CURRENT_TIMESTAMP,
                    volume = %s
                WHERE id = %s
            """, (
                analytics_data.get('yes_prices', ''),
                analytics_data.get('no_prices', ''),
                analytics_data.get('market_exists', False),
                analytics_data.get('is_boolean', False),
                analytics_data.get('yes_percentage', 0.00),
                analytics_data.get('contract_address', ''),
                analytics_data.get('status', 'в работе'),
                analytics_data.get('volume', 'New'),
                market_id
            ))
            conn.commit()
            logger.info(f"📊 Обновлены аналитические данные для рынка {market_id}")
            return True
    except Exception as e:
        logger.error(f"Ошибка обновления аналитических данных для рынка {market_id}: {e}")
        return False
    finally:
        conn.close()

def analyze_market_prices(slug):
    """Анализирует цены рынка (заглушка - здесь должна быть интеграция с ocr_screenshot_analyzer)"""
    try:
        # Здесь должна быть интеграция с вашим ocr_screenshot_analyzer
        # Пока возвращаем тестовые данные
        logger.info(f"🔍 Анализирую цены для рынка: {slug}")
        
        # Имитация данных из OCR анализатора
        analytics_data = {
            'yes_prices': '35.0K Yes, 20.6K Yes, 28.7K Yes, 43 Yes, 28.7K Yes, Yes 16¢',
            'no_prices': '4.7K No, 249 No, 4.7K No, 7.4K No, 13.9K No, 52.1K No, 4.7K No, 370No, 443 No, No 85¢',
            'market_exists': True,
            'is_boolean': True,
            'yes_percentage': 45.50,
            'contract_address': '',
            'status': 'в работе',
            'volume': 'New'
        }
        
        return analytics_data
        
    except Exception as e:
        logger.error(f"Ошибка анализа цен для рынка {slug}: {e}")
        return None

def analyze_markets():
    """Основная функция анализа рынков"""
    logger.info("🔍 Начинаю анализ рынков...")
    
    markets = get_markets_for_analysis()
    
    if not markets:
        logger.info("Нет рынков для анализа")
        return
    
    logger.info(f"📊 Найдено {len(markets)} рынков для анализа")
    
    for market in markets:
        try:
            logger.info(f"🔍 Анализирую рынок: {market['slug']}")
            
            # Анализируем цены
            analytics_data = analyze_market_prices(market['slug'])
            
            if analytics_data:
                # Обновляем данные в БД
                success = update_market_analytics(market['id'], analytics_data)
                
                if success:
                    # Отправляем уведомление
                    message = (
                        f"📊 <b>Анализ рынка завершен!</b>\n\n"
                        f"📋 Вопрос: {market['question']}\n"
                        f"🆔 ID: {market['id']}\n"
                        f"🔗 Slug: {market['slug']}\n"
                        f"📈 Yes цены: {analytics_data['yes_prices'][:100]}...\n"
                        f"📉 No цены: {analytics_data['no_prices'][:100]}...\n"
                        f"📊 Процент Yes: {analytics_data['yes_percentage']}%\n"
                        f"🌐 Ссылка: https://polymarket.com/market/{market['slug']}"
                    )
                    send_telegram_message(message)
                    
                    logger.info(f"✅ Анализ рынка {market['slug']} завершен")
                else:
                    logger.error(f"❌ Не удалось обновить данные для рынка {market['slug']}")
            else:
                logger.warning(f"⚠️ Не удалось получить данные для рынка {market['slug']}")
            
            # Пауза между анализами
            time.sleep(5)
            
        except Exception as e:
            logger.error(f"Ошибка анализа рынка {market['slug']}: {e}")

def main():
    logger.info("=== Запуск Market Analyzer ===")
    
    while True:
        try:
            analyze_markets()
            logger.info("💤 Ожидание 60 секунд перед следующим анализом...")
            time.sleep(60)
        except KeyboardInterrupt:
            logger.info("⏹️ Остановка Market Analyzer...")
            break
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
            time.sleep(30)
    
    logger.info("=== Market Analyzer остановлен ===")

if __name__ == "__main__":
    main() 