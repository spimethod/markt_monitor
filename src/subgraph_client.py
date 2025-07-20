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

# шаблон запроса — подставляем root-поле
QUERY_TEMPLATE = """
query GetNewMarkets($ts: Int!, $limit: Int!) {{
  {field}(
    first: $limit
    orderBy: creationTimestamp
    orderDirection: desc
    where: {{
      creationTimestamp_gt: $ts
      active: true
      acceptingOrders: true
    }}
  ) {{
    id
    question
    createdTimestamp
    active
    acceptingOrders
    tokens {{
      id
      outcome
      price
    }}
  }}
}}"""

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
            "ts": min_timestamp,
            "limit": 100,
        }
        
        # выбираем root-поле
        primary_field = config.polymarket.SUBGRAPH_FIELD.strip() or None
        field_candidates = [primary_field] if primary_field else ["markets", "clobMarkets", "marketEntities"]

        markets: list | None = None
        last_error = None
        for fld in field_candidates:
            if not fld:
                continue
            query_str = QUERY_TEMPLATE.format(field=fld)
            payload = {"query": query_str, "variables": variables}

            logger.info(f"🔗 Запрос новых рынков через Subgraph: {SUBGRAPH_URL}")
            logger.debug(f"   📋 Variables: {variables}")

            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.post(SUBGRAPH_URL, json=payload)
            data = response.json()

            if "errors" in data:
                last_error = data["errors"]
                # если ошибка из-за отсутствия поля — пробуем следующий вариант
                if any("has no field" in err.get("message", "") for err in data["errors"]):
                    logger.warning(f"Root-поле '{fld}' не найдено в субграфе, пробую другой вариант…")
                    continue
                else:
                    logger.error(f"❌ Ошибка от Subgraph API: {data['errors']}")
                    return None
            else:
                markets = data["data"].get(fld)
                if markets is not None:
                    break

        if markets is None:
            logger.error(f"❌ Subgraph не вернул рынки. Последняя ошибка: {last_error}")
            return None

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