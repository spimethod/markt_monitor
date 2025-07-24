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
from enum import Enum

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

class MarketStatus(Enum):
    CREATED = "created"           # Есть в Gamma API
    TRADING_READY = "trading_ready"  # Есть в CLOB API
    NOT_TRADEABLE = "not_tradeable"  # enableOrderBook = False

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

def get_market_status(slug):
    """
    Определяет статус рынка и получает все доступные данные
    """
    # 1. Проверяем Gamma API
    gamma_data = get_market_ids_from_gamma_api(slug)
    if not gamma_data[0]:  # condition_id не найден
        return {
            "status": "not_found",
            "error": "Market not found in Gamma API"
        }
    
    condition_id, token_ids, gamma_error = gamma_data
    
    # 2. Проверяем enableOrderBook через дополнительный запрос
    try:
        gamma_response = requests.get(
            "https://gamma-api.polymarket.com/markets",
            params={"slug": slug, "active": True},
            timeout=10
        )
        gamma_response.raise_for_status()
        markets = gamma_response.json()
        
        if markets:
            market = markets[0]
            enable_order_book = market.get("enableOrderBook", False)
            
            if not enable_order_book:
                return {
                    "status": MarketStatus.NOT_TRADEABLE.value,
                    "condition_id": condition_id,
                    "token_ids": token_ids,
                    "message": "Market created but trading disabled"
                }
        else:
            return {
                "status": "not_found",
                "error": "Market not found in Gamma API"
            }
    except Exception as e:
        logger.error(f"Ошибка проверки enableOrderBook: {e}")
        return {
            "status": "error",
            "error": f"Error checking enableOrderBook: {e}"
        }
    
    # 3. Проверяем CLOB API
    clob_data = get_market_ids_from_clob(slug)
    if clob_data[0]:  # condition_id найден в CLOB
        return {
            "status": MarketStatus.TRADING_READY.value,
            "condition_id": clob_data[0],
            "token_ids": clob_data[1],
            "message": "Market ready for trading"
        }
    
    # 4. Рынок создан, но еще не готов к торговле
    return {
        "status": MarketStatus.CREATED.value,
        "condition_id": condition_id,
        "token_ids": token_ids,
        "message": "Market created, waiting for trading activation",
        "estimated_wait_time": "Usually 5-30 minutes"
    }

def get_market_ids_from_clob(slug):
    """
    Получает condition_id и token_ids через CLOB API согласно документации
    """
    try:
        logger.info(f"🔍 Ищу данные для slug: {slug}")
        
        # Получаем все рынки из CLOB API
        clob_response = requests.get("https://clob.polymarket.com/markets", timeout=10)
        clob_response.raise_for_status()
        
        clob_data = clob_response.json()
        clob_markets = clob_data.get("data", [])
        
        logger.info(f"📊 Получено {len(clob_markets)} рынков из CLOB API")
        
        # Ищем рынок по slug в market_slug поле
        found_market = None
        for market in clob_markets:
            market_slug = market.get("market_slug")
            if market_slug == slug:
                found_market = market
                break
        
        if found_market:
            condition_id = found_market.get("condition_id")
            token_ids = [token["token_id"] for token in found_market.get("tokens", [])]
            
            logger.info(f"✅ Найден рынок в CLOB API:")
            logger.info(f"   Condition ID: {condition_id}")
            logger.info(f"   Token IDs: {token_ids}")
            
            return condition_id, token_ids, None
        else:
            # Логируем первые несколько slug'ов для отладки
            sample_slugs = [m.get("market_slug") for m in clob_markets[:5]]
            logger.warning(f"❌ Рынок {slug} не найден в CLOB API (не торгуется)")
            logger.warning(f"   Доступные slug'ы (первые 5): {sample_slugs}")
            
            return None, None, "Market not found in CLOB (not tradeable)"
            
    except Exception as e:
        logger.error(f"Ошибка получения данных из CLOB API: {e}")
        return None, None, f"CLOB API error: {e}"

def get_market_ids_from_gamma_api(slug):
    """
    Альтернативный способ получения condition_id через Gamma API параметры
    """
    try:
        logger.info(f"🔍 Пробую получить данные через Gamma API для slug: {slug}")
        
        # Пробуем получить данные через Gamma API с параметрами
        gamma_response = requests.get(
            "https://gamma-api.polymarket.com/markets",
            params={"slug": slug, "active": True},
            timeout=10
        )
        gamma_response.raise_for_status()
        
        markets = gamma_response.json()
        if markets:
            market = markets[0]
            
            # Используем правильные ключи из Gamma API
            condition_id = market.get("conditionId")  # Правильный ключ
            clob_token_ids = market.get("clobTokenIds", [])  # Правильный ключ
            
            logger.info(f"✅ Данные из Gamma API:")
            logger.info(f"   Condition ID: {condition_id}")
            logger.info(f"   Token IDs: {clob_token_ids}")
            
            return condition_id, clob_token_ids, None
        else:
            return None, None, "Market not found in Gamma API"
            
    except Exception as e:
        logger.error(f"Ошибка получения данных из Gamma API: {e}")
        return None, None, f"Gamma API error: {e}"

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
    slug TEXT,
    condition_id TEXT,
    clob_token_ids TEXT[],
    enable_order_book BOOLEAN,
    volume NUMERIC,
    liquidity NUMERIC,
    market_status TEXT DEFAULT 'created',
    trading_activated_at TIMESTAMP NULL
);
"""

INSERT_MARKET_SQL = """
INSERT INTO markets (id, question, created_at, active, slug, condition_id, clob_token_ids, enable_order_book, volume, liquidity, market_status)
VALUES %s
ON CONFLICT (id) DO UPDATE SET
    condition_id = EXCLUDED.condition_id,
    clob_token_ids = EXCLUDED.clob_token_ids,
    market_status = EXCLUDED.market_status,
    trading_activated_at = CASE 
        WHEN EXCLUDED.market_status = 'trading_ready' AND markets.market_status != 'trading_ready' 
        THEN NOW() 
        ELSE markets.trading_activated_at 
    END;
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

def get_pending_markets():
    """Получает список рынков, ожидающих активации торговли"""
    conn = connect_db()
    if not conn:
        return []
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, slug, created_at FROM markets WHERE market_status = 'created' ORDER BY created_at DESC"
            )
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Ошибка получения pending рынков: {e}")
        return []
    finally:
        conn.close()

def update_market_status(market_id, status, condition_id=None, clob_token_ids=None):
    """Обновляет статус рынка в БД"""
    conn = connect_db()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cursor:
            if status == MarketStatus.TRADING_READY.value:
                cursor.execute(
                    "UPDATE markets SET market_status = %s, trading_activated_at = NOW(), condition_id = %s, clob_token_ids = %s WHERE id = %s",
                    (status, condition_id, clob_token_ids, market_id)
                )
            else:
                cursor.execute(
                    "UPDATE markets SET market_status = %s WHERE id = %s",
                    (status, market_id)
                )
        conn.commit()
        logger.info(f"✅ Обновлен статус рынка {market_id}: {status}")
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления статуса рынка: {e}")
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
                    get_slug(market),
                    get_condition_id(market),
                    get_clob_token_ids(market),
                    get_enable_order_book(market),
                    get_volume(market),
                    get_liquidity(market),
                    get_market_status_from_data(market)
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
    """Удаляет рынки старше RETENTION_HOURS часов (кроме ожидающих активации)"""
    RETENTION_HOURS = 25
    conn = connect_db()
    if not conn:
        return
    
    try:
        with conn.cursor() as cursor:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=RETENTION_HOURS)
            
            # Удаляем только рынки, которые НЕ в статусе 'created' (не ожидают активации)
            cursor.execute(
                "DELETE FROM markets WHERE created_at < %s AND market_status != 'created'",
                (cutoff_time,)
            )
            deleted_count = cursor.rowcount
            conn.commit()
            if deleted_count > 0:
                logger.info(f"🗑️ Удалено {deleted_count} старых рынков (не ожидающих активации)")
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

def get_slug(market):
    """Извлекает slug рынка"""
    return market.get('slug')

def get_condition_id(market):
    """Извлекает condition_id из обогащенного market объекта"""
    return market.get('condition_id')

def get_clob_token_ids(market):
    """Извлекает clob_token_ids из обогащенного market объекта"""
    # Используем token_ids из обогащенного market объекта
    token_ids = market.get('clob_token_ids', [])
    
    # Убеждаемся, что это список строк
    if isinstance(token_ids, list):
        return [str(tid) for tid in token_ids if tid]
    return []

def get_enable_order_book(market):
    """Извлекает enable_order_book"""
    return market.get('enable_order_book') or market.get('enableOrderBook', False)

def get_volume(market):
    """Извлекает volume"""
    volume = market.get('volume')
    if volume is not None:
        try:
            return float(volume)
        except:
            return None
    return None

def get_liquidity(market):
    """Извлекает liquidity"""
    liquidity = market.get('liquidity')
    if liquidity is not None:
        try:
            return float(liquidity)
        except:
            return None
    return None

def get_market_status_from_data(market):
    """Определяет статус рынка из данных"""
    return market.get('market_status', MarketStatus.CREATED.value)

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
            
            # Определяем статус рынка
            slug = get_slug(market)
            status_info = get_market_status(slug)
            
            logger.info(f"📊 Статус рынка {slug}: {status_info['status']}")
            
            # Обогащаем market данными
            market['condition_id'] = status_info.get('condition_id')
            market['clob_token_ids'] = status_info.get('token_ids', [])
            market['market_status'] = status_info['status']
            
            new_markets.append(market)
            created_at = get_creation_time(market)
            
            # Логируем новый рынок
            logger.info(f"🆕 Новый рынок: {question}")
            logger.info(f"ID: {market_id}")
            logger.info(f"Время создания: {created_at}")
            logger.info(f"Активный: {get_active(market)}")
            logger.info(f"Slug: {get_slug(market)}")
            logger.info(f"Condition ID: {get_condition_id(market)}")
            logger.info(f"CLOB Token IDs: {get_clob_token_ids(market)}")
            logger.info(f"Enable Order Book: {get_enable_order_book(market)}")
            logger.info(f"Volume: {get_volume(market)}")
            logger.info(f"Liquidity: {get_liquidity(market)}")
            logger.info(f"Статус: {status_info['status']}")
            logger.info(f"Сообщение: {status_info.get('message', 'N/A')}")
            logger.info("---")
            
            # Отправляем уведомление в Telegram
            message = (
                f"🆕 <b>Новый рынок на Polymarket!</b>\n\n"
                f"📋 Вопрос: {question}\n"
                f"🆔 ID: {market_id}\n"
                f"⏰ Создан: {created_at}\n"
                f"🔗 Slug: {get_slug(market)}\n"
                f"📊 Активен: {'Да' if get_active(market) else 'Нет'}\n"
                f"📈 Объем: ${get_volume(market) or 'N/A'}\n"
                f"💰 Ликвидность: ${get_liquidity(market) or 'N/A'}\n"
                f"📚 Order Book: {'Да' if get_enable_order_book(market) else 'Нет'}\n"
                f"🔄 Статус: {status_info['status']}"
            )
            send_telegram_message(message)
        
        logger.info(f"📈 Статистика: {len(new_markets)} новых, {already_exists} уже в базе, {skipped_special} пропущено (Up or Down)")
        
        if new_markets:
            save_markets(new_markets)
        else:
            logger.info("Нет новых рынков. Жду...")
    except Exception as e:
        logger.error(f"Ошибка при запросе к Gamma Markets API: {e}")

def check_pending_markets():
    """Проверяет рынки, ожидающие активации торговли"""
    pending_markets = get_pending_markets()
    
    if not pending_markets:
        return
    
    logger.info(f"🔄 Проверяю {len(pending_markets)} рынков, ожидающих активации...")
    
    for market_id, slug, created_at in pending_markets:
        logger.info(f"🔍 Проверяю активацию для {slug} (ID: {market_id})")
        
        # Проверяем статус рынка
        status_info = get_market_status(slug)
        
        if status_info['status'] == MarketStatus.TRADING_READY.value:
            logger.info(f"✅ Торговля активирована для {slug}!")
            
            # Обновляем статус в БД
            update_market_status(
                market_id, 
                MarketStatus.TRADING_READY.value,
                status_info.get('condition_id'),
                status_info.get('token_ids', [])
            )
            
            # Отправляем уведомление
            message = (
                f"🎉 <b>Торговля активирована!</b>\n\n"
                f"📋 Рынок: {slug}\n"
                f"🆔 ID: {market_id}\n"
                f"⏰ Активирован: {datetime.now(timezone.utc)}\n"
                f"🆔 Condition ID: {status_info.get('condition_id')}\n"
                f"🔢 Token IDs: {len(status_info.get('token_ids', []))}"
            )
            send_telegram_message(message)
            
        elif status_info['status'] == MarketStatus.NOT_TRADEABLE.value:
            logger.info(f"❌ Торговля отключена для {slug}")
            update_market_status(market_id, MarketStatus.NOT_TRADEABLE.value)
            
        else:
            # Рынок все еще ожидает активации
            # Исправляем ошибку с timezone
            current_time = datetime.now(timezone.utc)
            if created_at.tzinfo is None:
                # Если created_at без timezone, добавляем UTC
                created_at = created_at.replace(tzinfo=timezone.utc)
            
            elapsed = current_time - created_at
            logger.info(f"⏳ {slug} все еще ожидает активации ({elapsed.total_seconds()/60:.1f} минут)")

def cleanup_inactive_markets():
    """Удаляет рынки, которые не активировались в течение 12 часов"""
    MAX_WAIT_HOURS = 12
    conn = connect_db()
    if not conn:
        return
    
    try:
        with conn.cursor() as cursor:
            # Находим рынки, которые созданы более 12 часов назад и все еще в статусе 'created'
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=MAX_WAIT_HOURS)
            
            cursor.execute("""
                SELECT id, slug, created_at, market_status 
                FROM markets 
                WHERE market_status = 'created' AND created_at < %s
            """, (cutoff_time,))
            
            inactive_markets = cursor.fetchall()
            
            if inactive_markets:
                logger.info(f"🗑️ Найдено {len(inactive_markets)} неактивных рынков (старше {MAX_WAIT_HOURS} часов)")
                
                for market_id, slug, created_at, status in inactive_markets:
                    elapsed_hours = (datetime.now(timezone.utc) - created_at).total_seconds() / 3600
                    logger.info(f"   Удаляю рынок {slug} (ID: {market_id}) - {elapsed_hours:.1f} часов ожидания")
                
                # Удаляем неактивные рынки
                cursor.execute("""
                    DELETE FROM markets 
                    WHERE market_status = 'created' AND created_at < %s
                """, (cutoff_time,))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    logger.info(f"✅ Удалено {deleted_count} неактивных рынков")
                    
                    # Отправляем уведомление в Telegram
                    message = (
                        f"🗑️ <b>Удалены неактивные рынки</b>\n\n"
                        f"⏰ Удалено: {deleted_count} рынков\n"
                        f"⏱️ Максимальное время ожидания: {MAX_WAIT_HOURS} часов\n"
                        f"📅 Время: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
                    )
                    send_telegram_message(message)
            else:
                logger.debug(f"✅ Нет неактивных рынков для удаления (проверка каждые {POLL_INTERVAL} секунд)")
                
    except Exception as e:
        logger.error(f"Ошибка удаления неактивных рынков: {e}")
    finally:
        conn.close()

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
            
            # Проверка активации pending рынков
            check_pending_markets()
            
            # Очищаем неактивные рынки (старше 12 часов)
            cleanup_inactive_markets()
            
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