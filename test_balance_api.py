#!/usr/bin/env python3
"""
Тест новой функциональности получения баланса через Polymarket Data API
"""

import asyncio
import sys
import os

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.polymarket_client import PolymarketClient
from loguru import logger

async def test_new_balance_functionality():
    """Тестирует новую функциональность получения баланса"""
    logger.info("🧪 Начинаем тестирование новой функциональности баланса")
    
    try:
        # Создаем клиент
        client = PolymarketClient()
        
        if not client.account:
            logger.error("❌ Аккаунт не инициализирован - проверьте PRIVATE_KEY")
            return
            
        logger.info(f"✅ Клиент инициализирован для адреса: {client.get_address()}")
        
        # Тестируем старый метод
        logger.info("\n📊 Тестирование общего метода get_account_balance():")
        balance = client.get_account_balance()
        if balance is not None:
            logger.info(f"✅ Баланс получен: ${balance:.6f}")
        else:
            logger.warning("⚠️ Не удалось получить баланс")
        
        # Тестируем новые методы отдельно
        user_address = client.get_address()
        if client.config.polymarket.POLYMARKET_PROXY_ADDRESS:
            user_address = client.config.polymarket.POLYMARKET_PROXY_ADDRESS
            
        if not user_address:
            logger.error("❌ Не удалось получить адрес пользователя")
            return
            
        logger.info(f"\n🔍 Тестирование новых API методов для адреса: {user_address}")
        
        # Тест 1: Стоимость позиций
        logger.info("\n📈 Тест 1: Получение стоимости позиций через /value API")
        positions_value = client._get_positions_value(user_address)
        if positions_value is not None:
            logger.info(f"✅ Стоимость позиций: ${positions_value:.6f}")
        else:
            logger.info("ℹ️ Стоимость позиций не найдена или равна 0")
            
        # Тест 2: Свободный USDC через proxy wallet
        logger.info("\n💰 Тест 2: Получение свободного USDC через proxy wallet")
        proxy_wallet, free_usdc = client._get_free_usdc_balance(user_address)
        if proxy_wallet:
            logger.info(f"🏦 Найден proxy wallet: {proxy_wallet}")
        if free_usdc is not None:
            logger.info(f"💵 Свободный USDC: ${free_usdc:.6f}")
        else:
            logger.info("ℹ️ Свободный USDC не найден")
            
        # Тест 3: Проверка RPC для proxy wallet
        if proxy_wallet:
            logger.info(f"\n🌐 Тест 3: Проверка USDC баланса через RPC для proxy wallet: {proxy_wallet}")
            rpc_balance = client._check_usdc_balance_for_address(proxy_wallet)
            if rpc_balance is not None and rpc_balance > 0:
                logger.info(f"✅ RPC баланс: ${rpc_balance:.6f}")
            else:
                logger.info("ℹ️ RPC баланс не найден или равен 0")
        
        # Итоговая сводка
        logger.info("\n📋 Итоговая сводка:")
        total_value = 0.0
        if positions_value:
            total_value += positions_value
            logger.info(f"  📊 Стоимость позиций: ${positions_value:.6f}")
        if free_usdc:
            total_value += free_usdc
            logger.info(f"  💵 Свободный USDC: ${free_usdc:.6f}")
        if total_value > 0:
            logger.info(f"  💰 Общая стоимость: ${total_value:.6f}")
        else:
            logger.info("  ⚠️ Баланс не найден - используется fallback")
            
        logger.info("✅ Тестирование завершено")
        
    except Exception as e:
        logger.error(f"❌ Ошибка во время тестирования: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(test_new_balance_functionality()) 