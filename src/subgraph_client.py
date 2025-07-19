import asyncio
import time
from datetime import datetime
import httpx
from logging import getLogger

logger = getLogger(__name__)

# Формируем URL сабграфа
from src.config.settings import config

if config.polymarket.THEGRAPH_API_KEY:
    SUBGRAPH_URL = (
        f"https://gateway.thegraph.com/api/{config.polymarket.THEGRAPH_API_KEY}" \
        f"/subgraphs/id/{config.polymarket.SUBGRAPH_ID}"
    )
else:
    # Fallback: старый hosted service (может быть отключён)
    SUBGRAPH_URL = "https://api.thegraph.com/subgraphs/name/polymarket/polymarket-v3/"

# GraphQL-запрос для получения новых рынков
MARKETS_QUERY = """
query GetNewMarkets($min_timestamp: BigInt!, $limit: Int!) {
  markets(
    first: $limit,
    orderBy: createdTimestamp,
    orderDirection: desc,
    where: {
      createdTimestamp_gt: $min_timestamp,
      active: true,
      acceptingOrders: true
    }
  ) {
    id
    question
    createdTimestamp
    tokens {
      id
      name
      outcome
      price
    }
    conditionId
    active
    acceptingOrders
  }
}
"""

async def fetch_new_markets(max_age_minutes: int = 10) -> list | None:
    """
    Получает рынки, созданные за последние N минут, используя Subgraph.

    Args:
        max_age_minutes: Максимальный возраст рынков в минутах.

    Returns:
        Список новых рынков, если запрос успешен.
        None, если произошла ошибка сети или API.
    """
    try:
        now = int(time.time())
        min_timestamp = now - (max_age_minutes * 60)

        variables = {
            "min_timestamp": str(min_timestamp),  # BigInt как строка
            "limit": 100
        }
        
        payload = {
            "query": MARKETS_QUERY,
            "variables": variables
        }

        logger.info(f"🔗 Запрос новых рынков через Subgraph: {SUBGRAPH_URL}")
        logger.debug(f"   📋 Variables: {variables}")

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.post(SUBGRAPH_URL, json=payload)
            response.raise_for_status()

        data = response.json()

        if "errors" in data:
            logger.error(f"❌ Ошибка от Subgraph API: {data['errors']}")
            return None

        if "data" not in data or "markets" not in data["data"]:
            logger.error(f"❌ Неожиданная структура ответа от Subgraph: {data}")
            return None

        markets = data["data"]["markets"]
        logger.info(f"🎯 Subgraph вернул {len(markets)} новых рынков (≤{max_age_minutes} мин)")
        return markets

    except httpx.HTTPStatusError as e:
        logger.error(f"❌ Ошибка статуса HTTP при запросе к Subgraph: {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"❌ Ошибка сети при запросе к Subgraph: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Непредвиденная ошибка при получении данных из Subgraph: {e}")
        return None

if __name__ == '__main__':
    async def main():
        print("Тестирование Subgraph клиента...")
        new_markets = await fetch_new_markets(max_age_minutes=60)
        if new_markets is not None:
            print(f"Найдено {len(new_markets)} рынков.")
            for market in new_markets:
                created_dt = datetime.fromtimestamp(int(market['createdTimestamp']))
                print(f"- {market['question']} (Создан: {created_dt.strftime('%Y-%m-%d %H:%M')})")
        else:
            print("Не удалось получить рынки.")

    asyncio.run(main()) 