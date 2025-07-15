#!/usr/bin/env python3
"""
Тест новой функциональности получения баланса через публичные Polymarket Data API
Работает без приватного ключа, используя публичные адреса
"""

import sys
import os
import requests

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from loguru import logger

def test_polymarket_data_api():
    """Тестирует Polymarket Data API с публичными адресами"""
    logger.info("🧪 Тестирование Polymarket Data API")
    
    # Известный публичный адрес с активностью на Polymarket
    test_addresses = [
        "0x0000000000000000000000000000000000000000",  # Нулевой адрес для проверки пустого ответа
        "0x190Cc00825739D2a20DA3036a8D85419342C84E",  # Наш proxy адрес из конфига
    ]
    
    for test_address in test_addresses:
        logger.info(f"\n🔍 Тестирование адреса: {test_address}")
        
        # Тест 1: API /value (общая стоимость позиций)
        logger.info("📊 Тест 1: /value API")
        try:
            value_url = f"https://data-api.polymarket.com/value?user={test_address}"
            logger.info(f"📡 Запрос: {value_url}")
            
            response = requests.get(value_url, timeout=10)
            logger.info(f"📊 Статус: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"📋 Ответ: {data}")
                
                if isinstance(data, list) and len(data) > 0:
                    user_data = data[0]
                    if 'value' in user_data:
                        value = float(user_data['value'])
                        logger.info(f"✅ Стоимость позиций: ${value:.6f}")
                    else:
                        logger.info("ℹ️ Поле 'value' не найдено")
                elif isinstance(data, list) and len(data) == 0:
                    logger.info("ℹ️ Позиции не найдены (пустой массив)")
                else:
                    logger.warning(f"⚠️ Неожиданная структура: {type(data)}")
            else:
                logger.warning(f"⚠️ HTTP ошибка: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка /value API: {e}")
        
        # Тест 2: API /positions (детальные позиции)
        logger.info("\n📈 Тест 2: /positions API")
        try:
            positions_url = f"https://data-api.polymarket.com/positions?user={test_address}"
            logger.info(f"📡 Запрос: {positions_url}")
            
            response = requests.get(positions_url, timeout=10)
            logger.info(f"📊 Статус: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"📋 Тип ответа: {type(data)}")
                
                if isinstance(data, list):
                    logger.info(f"📋 Количество позиций: {len(data)}")
                    
                    if len(data) > 0:
                        first_position = data[0]
                        logger.info(f"📋 Первая позиция (ключи): {list(first_position.keys()) if isinstance(first_position, dict) else 'не словарь'}")
                        
                        if isinstance(first_position, dict) and 'proxyWallet' in first_position:
                            proxy_wallet = first_position['proxyWallet']
                            logger.info(f"🏦 Найден proxy wallet: {proxy_wallet}")
                        else:
                            logger.info("ℹ️ proxyWallet не найден в первой позиции")
                            
                        # Показываем структуру первой позиции
                        if isinstance(first_position, dict):
                            relevant_fields = ['proxyWallet', 'initialValue', 'currentValue', 'cashPnl', 'value']
                            logger.info("📋 Релевантные поля в первой позиции:")
                            for field in relevant_fields:
                                if field in first_position:
                                    logger.info(f"  • {field}: {first_position[field]}")
                    else:
                        logger.info("ℹ️ Позиции не найдены (пустой массив)")
                else:
                    logger.warning(f"⚠️ Неожиданная структура: {type(data)}")
            else:
                logger.warning(f"⚠️ HTTP ошибка: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка /positions API: {e}")

def test_usdc_contracts():
    """Тестирует проверку USDC контрактов через RPC"""
    logger.info("\n🌐 Тестирование USDC контрактов через RPC")
    
    # Тестовые адреса
    test_proxy_wallet = "0x190Cc00825739D2a20DA3036a8D85419342C84E"
    
    # USDC контракты
    usdc_contracts = [
        ("Native USDC", "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"),
        ("Bridged USDC", "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"),
    ]
    
    # RPC endpoints
    rpc_endpoints = [
        "https://polygon-rpc.com",
        "https://polygon.llamarpc.com",
    ]
    
    logger.info(f"🔍 Проверка USDC для адреса: {test_proxy_wallet}")
    
    for contract_name, contract_addr in usdc_contracts:
        logger.info(f"\n📄 Проверка {contract_name}: {contract_addr}")
        
        # Формируем данные для вызова balanceOf
        function_signature = "0x70a08231"  # balanceOf(address)
        padded_address = test_proxy_wallet.replace("0x", "").lower().zfill(64)
        call_data = function_signature + padded_address
        
        for rpc_url in rpc_endpoints:
            try:
                logger.info(f"🌐 RPC: {rpc_url}")
                
                payload = {
                    "jsonrpc": "2.0",
                    "method": "eth_call",
                    "params": [{
                        "to": contract_addr,
                        "data": call_data
                    }, "latest"],
                    "id": 1
                }
                
                response = requests.post(
                    rpc_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=10
                )
                
                logger.info(f"📊 Статус: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    result = data.get("result", "0x0")
                    logger.info(f"📋 Result: {result}")
                    
                    if result and result != "0x0" and not result.endswith("0" * 60):
                        balance_wei = int(result, 16)
                        balance_usdc = balance_wei / (10 ** 6)
                        logger.info(f"✅ USDC баланс: ${balance_usdc:.6f}")
                        break  # Найден баланс, переходим к следующему контракту
                    else:
                        logger.info("ℹ️ Нулевой баланс")
                else:
                    logger.warning(f"⚠️ HTTP ошибка: {response.status_code}")
                    
            except Exception as e:
                logger.error(f"❌ Ошибка RPC {rpc_url}: {e}")

if __name__ == "__main__":
    test_polymarket_data_api()
    test_usdc_contracts()
    logger.info("✅ Тестирование публичных API завершено") 