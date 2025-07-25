import requests
import json
from loguru import logger

# === Конфиг ===
API_URL = "https://gamma-api.polymarket.com/markets"

def debug_api_response():
    """Диагностирует ответ API для выяснения проблемы с пропущенными рынками"""
    
    params = {
        'active': True,
        'limit': 5,
        'order': 'startDate',
        'ascending': False
    }
    
    try:
        logger.info("🔍 Диагностика API ответа...")
        response = requests.get(API_URL, params=params, timeout=10)
        response.raise_for_status()
        markets = response.json()
        
        logger.info(f"📊 Получено {len(markets)} рынков из API")
        
        for i, market in enumerate(markets):
            logger.info(f"\n=== Рынок {i+1} ===")
            logger.info(f"ID: {market.get('id')}")
            logger.info(f"Question: {market.get('question')}")
            logger.info(f"Slug: {market.get('slug')}")
            logger.info(f"Active: {market.get('active')}")
            logger.info(f"EnableOrderBook: {market.get('enableOrderBook')}")
            logger.info(f"CreatedAt: {market.get('createdAt')}")
            
            # Проверяем обязательные поля
            market_id = market.get('id')
            question = market.get('question')
            slug = market.get('slug')
            
            missing_fields = []
            if not market_id:
                missing_fields.append('id')
            if not question:
                missing_fields.append('question')
            if not slug:
                missing_fields.append('slug')
            
            if missing_fields:
                logger.warning(f"❌ Отсутствуют обязательные поля: {missing_fields}")
            else:
                logger.info("✅ Все обязательные поля присутствуют")
            
            # Проверяем фильтр "Up or Down"
            question_text = question or ""
            skip_prefixes = [
                "Bitcoin Up or Down",
                "Ethereum Up or Down", 
                "Solana Up or Down",
                "XRP Up or Down"
            ]
            
            if any(question_text.startswith(prefix) for prefix in skip_prefixes):
                logger.warning(f"⚠️ Рынок будет пропущен (Up or Down): {question_text}")
            else:
                logger.info("✅ Рынок не попадает под фильтр Up or Down")
        
        # Показываем полный JSON для первого рынка
        if markets:
            logger.info(f"\n📋 Полный JSON первого рынка:")
            logger.info(json.dumps(markets[0], indent=2, ensure_ascii=False))
            
    except Exception as e:
        logger.error(f"❌ Ошибка диагностики API: {e}")

if __name__ == "__main__":
    debug_api_response() 