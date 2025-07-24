import requests
import time
from datetime import datetime, timezone

def test_market_status():
    """Тестирует логику определения статуса рынков"""
    
    # Тестовые рынки из ваших логов
    test_markets = [
        "houthi-strike-on-israel-by-august-31-996",
        "syria-strikes-israel-by-december-31"
    ]
    
    print("🧪 Тестирование логики определения статуса рынков")
    print("=" * 60)
    
    for slug in test_markets:
        print(f"\n🔍 Тестирую рынок: {slug}")
        
        # 1. Проверяем Gamma API
        print("   📊 Проверяю Gamma API...")
        try:
            gamma_response = requests.get(
                "https://gamma-api.polymarket.com/markets",
                params={"slug": slug, "active": True},
                timeout=10
            )
            gamma_response.raise_for_status()
            gamma_markets = gamma_response.json()
            
            if gamma_markets:
                market = gamma_markets[0]
                condition_id = market.get("conditionId")
                enable_order_book = market.get("enableOrderBook", False)
                
                print(f"   ✅ Найден в Gamma API:")
                print(f"      Condition ID: {condition_id}")
                print(f"      Enable Order Book: {enable_order_book}")
                
                if not enable_order_book:
                    print(f"   ❌ Торговля отключена (enableOrderBook = False)")
                    continue
            else:
                print(f"   ❌ Не найден в Gamma API")
                continue
                
        except Exception as e:
            print(f"   ❌ Ошибка Gamma API: {e}")
            continue
        
        # 2. Проверяем CLOB API
        print("   📊 Проверяю CLOB API...")
        try:
            clob_response = requests.get("https://clob.polymarket.com/markets", timeout=10)
            clob_response.raise_for_status()
            clob_data = clob_response.json()
            clob_markets = clob_data.get("data", [])
            
            # Ищем рынок по slug
            found_in_clob = False
            for market in clob_markets:
                if market.get("market_slug") == slug:
                    clob_condition_id = market.get("condition_id")
                    clob_token_ids = [token["token_id"] for token in market.get("tokens", [])]
                    
                    print(f"   ✅ Найден в CLOB API:")
                    print(f"      Condition ID: {clob_condition_id}")
                    print(f"      Token IDs: {clob_token_ids}")
                    print(f"   🎉 Статус: TRADING_READY")
                    found_in_clob = True
                    break
            
            if not found_in_clob:
                print(f"   ⏳ Не найден в CLOB API (ожидает активации)")
                print(f"   📊 Статус: CREATED (ожидает активации торговли)")
                
        except Exception as e:
            print(f"   ❌ Ошибка CLOB API: {e}")
            print(f"   📊 Статус: CREATED (ошибка проверки CLOB)")
    
    print("\n" + "=" * 60)
    print("✅ Тест завершен")

def test_new_market_detection():
    """Тестирует обнаружение новых рынков"""
    
    print("\n🧪 Тестирование обнаружения новых рынков")
    print("=" * 60)
    
    try:
        # Получаем последние рынки из Gamma API
        response = requests.get(
            "https://gamma-api.polymarket.com/markets",
            params={
                'active': True,
                'limit': 5,
                'order': 'startDate',
                'ascending': False
            },
            timeout=10
        )
        response.raise_for_status()
        markets = response.json()
        
        print(f"📊 Получено {len(markets)} рынков из Gamma API")
        
        for i, market in enumerate(markets[:3]):  # Показываем первые 3
            question = market.get('question', 'N/A')
            slug = market.get('slug', 'N/A')
            market_id = market.get('id', 'N/A')
            created_at = market.get('createdAt', 'N/A')
            
            print(f"\n🆕 Рынок {i+1}:")
            print(f"   ID: {market_id}")
            print(f"   Вопрос: {question}")
            print(f"   Slug: {slug}")
            print(f"   Создан: {created_at}")
            
            # Проверяем статус
            if slug != 'N/A':
                print(f"   🔍 Проверяю статус...")
                
                # Быстрая проверка CLOB
                try:
                    clob_response = requests.get("https://clob.polymarket.com/markets", timeout=5)
                    clob_data = clob_response.json()
                    clob_markets = clob_data.get("data", [])
                    
                    found_in_clob = any(m.get("market_slug") == slug for m in clob_markets)
                    
                    if found_in_clob:
                        print(f"   ✅ Статус: TRADING_READY")
                    else:
                        print(f"   ⏳ Статус: CREATED (ожидает активации)")
                        
                except:
                    print(f"   ❓ Статус: Неизвестен (ошибка проверки CLOB)")
            
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")

if __name__ == "__main__":
    test_market_status()
    test_new_market_detection() 