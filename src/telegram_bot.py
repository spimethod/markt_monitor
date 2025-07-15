"""
Telegram бот для уведомлений и управления торговым ботом
Поддерживает команды управления и отправку уведомлений о торговых операциях
"""

from datetime import datetime
from typing import Dict, List, Optional, Union, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode
from loguru import logger

from src.config.settings import config


class TelegramNotifier:
    """Класс для отправки уведомлений в Telegram"""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.app = None
        self.bot_status = "stopped"
        self.trading_enabled = True
        self.trading_engine = None  # Ссылка на торговый движок

        self._initialize_bot()

    def set_trading_engine(self, trading_engine):
        """Установка ссылки на торговый движок"""
        self.trading_engine = trading_engine

    def _initialize_bot(self):
        """Инициализация Telegram бота"""
        try:
            self.app = Application.builder().token(self.bot_token).build()

            # Регистрируем обработчики команд
            self.app.add_handler(CommandHandler("start", self._cmd_start))
            self.app.add_handler(CommandHandler("status", self._cmd_status))
            self.app.add_handler(CommandHandler("balance", self._cmd_balance))
            self.app.add_handler(CommandHandler("positions", self._cmd_positions))
            self.app.add_handler(CommandHandler("stop", self._cmd_stop_trading))
            self.app.add_handler(
                CommandHandler("start_trading", self._cmd_start_trading)
            )
            self.app.add_handler(CommandHandler("config", self._cmd_config))
            self.app.add_handler(CommandHandler("logs", self._cmd_logs))
            self.app.add_handler(CommandHandler("help", self._cmd_help))

            # Обработчики inline кнопок
            self.app.add_handler(CallbackQueryHandler(self._handle_callback))

            logger.info("Telegram бот инициализирован")

        except Exception as e:
            logger.error(f"Ошибка инициализации Telegram бота: {e}")
            raise

    async def start_bot(self):
        """Запуск Telegram бота"""
        try:
            if self.app:
                await self.app.initialize()
                await self.app.start()

                # Отправляем уведомление о запуске
                await self.send_startup_notification()

                self.bot_status = "running"
                logger.info("Telegram бот запущен")

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(f"Ошибка запуска Telegram бота: {e}")
            raise

    async def stop_bot(self):
        """Остановка Telegram бота"""
        try:
            if self.app:
                await self.app.stop()
                await self.app.shutdown()

            self.bot_status = "stopped"
            logger.info("Telegram бот остановлен")

        except Exception as e:
            logger.error(f"Ошибка остановки Telegram бота: {e}")

    async def send_message(
        self, text: str, parse_mode: str = ParseMode.HTML, reply_markup=None
    ):
        """Отправка сообщения в Telegram"""
        try:
            if self.app and self.app.bot:
                await self.app.bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True,
                )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(f"Ошибка отправки сообщения в Telegram: {e}")

    async def send_startup_notification(self):
        """Уведомление о запуске бота"""
        text = f"""
🚀 <b>Polymarket Trading Bot запущен</b>

📊 <b>Конфигурация:</b>
• Размер позиции: ${config.trading.POSITION_SIZE_USD}
• Цель прибыли: {config.trading.PROFIT_TARGET_PERCENT}%
• Стратегия: {config.trading.TRADING_STRATEGY}
• Сторона: {config.trading.POSITION_SIDE}
• Макс. позиций: {config.trading.MAX_OPEN_POSITIONS}

⏰ <i>Время запуска: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</i>
        """

        keyboard = [
            [InlineKeyboardButton("📊 Статус", callback_data="status")],
            [InlineKeyboardButton("💰 Баланс", callback_data="balance")],
            [InlineKeyboardButton("📋 Позиции", callback_data="positions")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="config")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await self.send_message(text, reply_markup=reply_markup)

    async def send_new_market_notification(self, market_data: Dict):
        """Уведомление о новом рынке"""
        if not config.telegram.NOTIFY_NEW_MARKETS:
            return

        text = f"""
🆕 <b>Новый рынок обнаружен</b>

📋 <b>Название:</b> {market_data.get('question', 'N/A')}
🏷️ <b>ID:</b> <code>{market_data.get('id', 'N/A')}</code>
💰 <b>Ликвидность:</b> ${market_data.get('liquidity', 0):.2f}
📊 <b>Объем 24ч:</b> ${market_data.get('volume24hr', 0):.2f}

⏰ <i>{datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
        """

        await self.send_message(text)

    async def send_trade_notification(self, trade_data: Dict):
        """Уведомление о сделке"""
        if not config.telegram.NOTIFY_TRADES:
            return

        action = "🟢 ПОКУПКА" if trade_data.get("side") == "BUY" else "🔴 ПРОДАЖА"

        text = f"""
{action} <b>Ордер размещен</b>

🏷️ <b>ID:</b> <code>{trade_data.get('order_id', 'N/A')}</code>
💱 <b>Токен:</b> <code>{trade_data.get('token_id', 'N/A')[:20]}...</code>
📊 <b>Размер:</b> {trade_data.get('size', 0):.2f}
💰 <b>Цена:</b> ${trade_data.get('price', 0):.4f}
💵 <b>Сумма:</b> ${trade_data.get('size', 0) * trade_data.get('price', 0):.2f}

⏰ <i>{datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
        """

        await self.send_message(text)

    async def send_profit_notification(self, profit_data: Dict):
        """Уведомление о прибыли"""
        if not config.telegram.NOTIFY_PROFITS:
            return

        profit_percent = profit_data.get("profit_percent", 0)
        profit_emoji = "💚" if profit_percent > 0 else "❤️"

        text = f"""
{profit_emoji} <b>Позиция закрыта</b>

🏷️ <b>ID:</b> <code>{profit_data.get('order_id', 'N/A')}</code>
📊 <b>Прибыль:</b> {profit_percent:.2f}%
💰 <b>Сумма P&L:</b> ${profit_data.get('pnl_amount', 0):.2f}
📝 <b>Причина:</b> {profit_data.get('reason', 'N/A')}

⏰ <i>{datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
        """

        keyboard = [
            [InlineKeyboardButton("📊 Статус", callback_data="status")],
            [InlineKeyboardButton("📋 Позиции", callback_data="positions")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await self.send_message(text, reply_markup=reply_markup)

    async def send_error_notification(self, error_data: Dict):
        """Уведомление об ошибке"""
        if not config.telegram.NOTIFY_ERRORS:
            return

        text = f"""
🚨 <b>Ошибка</b>

📝 <b>Описание:</b> {error_data.get('message', 'N/A')}
🔧 <b>Компонент:</b> {error_data.get('component', 'N/A')}
⚠️ <b>Уровень:</b> {error_data.get('level', 'ERROR')}

⏰ <i>{datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
        """

        await self.send_message(text)

    async def _get_current_stats(self) -> Dict:
        """Получение текущей статистики от торгового движка"""
        try:
            if self.trading_engine:
                stats = await self.trading_engine.get_stats()
                # Добавляем информацию о статусе торговли
                stats["is_running"] = self.trading_engine.is_running
                stats["is_trading_enabled"] = self.trading_engine.is_trading_enabled
                return stats
            else:
                logger.warning("Trading engine не установлен в telegram боте")
        except Exception as e:
            logger.error(f"Ошибка получения статистики от торгового движка: {e}")
            
        # Возвращаем пустую статистику если не удалось получить данные
        return {
            "total_trades": 0,
            "successful_trades": 0,
            "total_profit": 0.0,
            "daily_trades": 0,
            "is_running": False,
            "is_trading_enabled": False,
            "open_positions": 0,
        }

    def _get_current_balance(self) -> Optional[float]:
        """Получение текущего баланса"""
        try:
            if self.trading_engine and hasattr(self.trading_engine, "client"):
                balance = self.trading_engine.client.get_account_balance()
                logger.debug(f"Получен баланс: ${balance}")
                return balance
            else:
                logger.warning("Trading engine или client не доступен для получения баланса")
        except Exception as e:
            logger.error(f"Ошибка получения баланса: {e}")
        return None

    def _get_detailed_balance(self) -> Dict[str, Any]:
        """Получение детального баланса через Polymarket Data API"""
        try:
            if not self.trading_engine or not hasattr(self.trading_engine, "client"):
                logger.warning("Trading engine не доступен для получения детального баланса")
                return {"free_usdc": None, "positions_value": None, "total": None}
            
            client = self.trading_engine.client
            if not client.account:
                logger.warning("Account не инициализирован для получения детального баланса")
                return {"free_usdc": None, "positions_value": None, "total": None}
            
            # Получаем адреса для проверки
            addresses_to_check = []
            if client.config.polymarket.POLYMARKET_PROXY_ADDRESS:
                addresses_to_check.append(client.config.polymarket.POLYMARKET_PROXY_ADDRESS)
            main_address = client.get_address()
            if main_address:
                addresses_to_check.append(main_address)
            
            if not addresses_to_check:
                logger.warning("Нет адресов для проверки детального баланса")
                return {"free_usdc": None, "positions_value": None, "total": None}
            
            logger.debug(f"Проверяем детальный баланс для {len(addresses_to_check)} адресов")
            
            # Пробуем для каждого адреса
            for user_address in addresses_to_check:
                try:
                    # Получаем стоимость позиций
                    positions_value = client._get_positions_value(user_address)
                    
                    # Получаем свободный USDC
                    proxy_wallet, free_usdc = client._get_free_usdc_balance(user_address)
                    
                    # Проверяем прямой баланс USDC
                    direct_usdc = client._check_usdc_balance_for_address(user_address)
                    
                    if positions_value is not None or free_usdc is not None or direct_usdc is not None:
                        total = 0.0
                        final_free_usdc = 0.0
                        final_positions_value = positions_value or 0.0
                        
                        # Используем наибольшее значение USDC
                        if free_usdc and free_usdc > 0:
                            final_free_usdc = free_usdc
                        elif direct_usdc and direct_usdc > 0:
                            final_free_usdc = direct_usdc
                        
                        total = final_positions_value + final_free_usdc
                        
                        result = {
                            "free_usdc": final_free_usdc,
                            "positions_value": final_positions_value,
                            "total": total if total > 0 else None,
                            "proxy_wallet": proxy_wallet,
                            "checked_address": user_address
                        }
                        
                        logger.debug(f"Детальный баланс получен: {result}")
                        return result
                        
                except Exception as addr_e:
                    logger.warning(f"Ошибка проверки адреса {user_address}: {addr_e}")
                    continue
            
            logger.info("Детальный баланс не найден ни на одном адресе")
            return {"free_usdc": None, "positions_value": None, "total": None}
            
        except Exception as e:
            logger.error(f"Критическая ошибка получения детального баланса: {e}")
            return {"free_usdc": None, "positions_value": None, "total": None}

    def _get_open_positions(self) -> List[Dict]:
        """Получение открытых позиций"""
        if self.trading_engine and hasattr(self.trading_engine, "client"):
            return [
                p
                for p in self.trading_engine.client.active_positions.values()
                if p["status"] == "open"
            ]
        return []

    def _format_timestamp(self, timestamp: Union[datetime, str, None]) -> str:
        """Безопасное форматирование timestamp"""
        if isinstance(timestamp, datetime):
            return timestamp.strftime("%Y-%m-%d %H:%M")
        if isinstance(timestamp, str):
            try:
                # Попытка парсинга строки в datetime
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                return dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, AttributeError):
                return timestamp[:16] if len(timestamp) > 16 else timestamp
        return "N/A"

    # Обработчики команд
    async def _cmd_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):  # pylint: disable=unused-argument
        """Команда /start"""
        if not update.message:
            return

        text = """
👋 <b>Добро пожаловать в Polymarket Trading Bot!</b>

🤖 Этот бот автоматически торгует на Polymarket, покупая позиции NO на новых рынках.

📋 <b>Доступные команды:</b>
/status - Статус бота
/balance - Баланс аккаунта
/positions - Открытые позиции
/stop - Остановить торговлю
/start_trading - Запустить торговлю
/config - Конфигурация
/logs - Последние логи
/help - Справка

🚀 Бот готов к работе!
        """

        keyboard = [
            [InlineKeyboardButton("📊 Статус", callback_data="status")],
            [InlineKeyboardButton("💰 Баланс", callback_data="balance")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )

    async def _cmd_status(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):  # pylint: disable=unused-argument
        """Команда /status"""
        if not update.message:
            return

        stats = await self._get_current_stats()

        # Получаем детальный баланс
        detailed_balance = self._get_detailed_balance()
        balance_text = ""
        
        if detailed_balance["total"] is not None:
            balance_text = f"""💰 <b>Баланс (через Polymarket API):</b>
• Свободный USDC: ${detailed_balance['free_usdc']:.2f}
• Стоимость позиций: ${detailed_balance['positions_value']:.2f}
• Общий баланс: ${detailed_balance['total']:.2f}"""
            if detailed_balance.get("proxy_wallet"):
                balance_text += f"\n• Proxy Wallet: {detailed_balance['proxy_wallet'][:10]}..."
        else:
            fallback_balance = self._get_current_balance() or 0
            balance_text = f"💰 <b>Баланс (fallback):</b> ${fallback_balance:.2f}"

        # Получаем статус базы данных
        db_status_text = ""
        if self.trading_engine and hasattr(self.trading_engine, "client") and hasattr(self.trading_engine.client, "db_manager"):
            db_status = self.trading_engine.client.db_manager.get_database_status()
            db_emoji = "🗄️" if db_status["engine_type"] == "PostgreSQL" else "📁" if db_status["engine_type"] == "SQLite" else "❌"
            db_status_text = f"\n{db_emoji} <b>База данных:</b> {db_status['engine_type']}"
            if db_status.get("using_sqlite_fallback"):
                db_status_text += " (fallback)"

        text = f"""
📊 <b>Статус бота</b>

🤖 <b>Состояние:</b> {self.bot_status}
🔄 <b>Торговля:</b> {'Включена' if stats.get('is_trading_enabled', False) else 'Отключена'}
📈 <b>Открытых позиций:</b> {stats.get('open_positions', 0)}{db_status_text}
{balance_text}

📋 <b>Сегодня:</b>
• Сделок: {stats.get('daily_trades', 0)}
• Прибыль: ${stats.get('total_profit', 0):.2f}
• Успешных: {stats.get('successful_trades', 0)}/{stats.get('total_trades', 0)}

⏰ <i>Последнее обновление: {datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
        """

        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data="status")],
            [InlineKeyboardButton("📋 Позиции", callback_data="positions")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )

    async def _cmd_balance(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):  # pylint: disable=unused-argument
        """Команда /balance"""
        if not update.message:
            return

        balance = self._get_current_balance()
        stats = await self._get_current_stats()
        open_positions = self._get_open_positions()

        # Рассчитываем средства в позициях
        in_positions = sum(p.get("size", 0) * p.get("price", 0) for p in open_positions)

        text = f"""
💰 <b>Баланс аккаунта</b>

💵 <b>USDC:</b> ${balance or 0:.2f}
📊 <b>В позициях:</b> ${in_positions:.2f}
💸 <b>Доступно:</b> ${(balance or 0) - in_positions:.2f}

📈 <b>P&L сегодня:</b> ${stats.get('total_profit', 0):.2f}
📊 <b>Всего сделок:</b> {stats.get('total_trades', 0)}

⏰ <i>Последнее обновление: {datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
        """

        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def _cmd_positions(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):  # pylint: disable=unused-argument
        """Команда /positions"""
        if not update.message:
            return

        open_positions = self._get_open_positions()

        if not open_positions:
            text = f"""
📋 <b>Открытые позиции</b>

🔍 <i>Нет открытых позиций</i>

⏰ <i>Последнее обновление: {datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
            """
        else:
            text = "📋 <b>Открытые позиции</b>\n\n"

            for i, position in enumerate(
                open_positions[:5], 1
            ):  # Показываем максимум 5 позиций
                timestamp = position.get("timestamp")
                time_str = self._format_timestamp(timestamp)

                text += f"""
<b>{i}.</b> {position.get('side', 'N/A')} {position.get('size', 0):.2f}
💰 Цена: ${position.get('price', 0):.4f}
⏰ Время: {time_str}
🏷️ ID: <code>{position.get('order_id', 'N/A')[:8]}...</code>

"""

            if len(open_positions) > 5:
                text += f"<i>... и еще {len(open_positions) - 5} позиций</i>\n\n"

            text += f"⏰ <i>Последнее обновление: {datetime.utcnow().strftime('%H:%M:%S')} UTC</i>"

        keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="positions")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )

    async def _cmd_stop_trading(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):  # pylint: disable=unused-argument
        """Команда /stop"""
        if not update.message:
            return

        if self.trading_engine:
            self.trading_engine.disable_trading()

        self.trading_enabled = False

        text = f"""
⏹️ <b>Торговля остановлена</b>

🚫 Бот больше не будет открывать новые позиции
📋 Существующие позиции остаются активными
🔄 Для возобновления используйте /start_trading

⏰ <i>{datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
        """

        keyboard = [
            [
                InlineKeyboardButton(
                    "▶️ Запустить торговлю", callback_data="start_trading"
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )

    async def _cmd_start_trading(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):  # pylint: disable=unused-argument
        """Команда /start_trading"""
        if not update.message:
            return

        if self.trading_engine:
            self.trading_engine.enable_trading()

        self.trading_enabled = True

        text = f"""
▶️ <b>Торговля запущена</b>

✅ Бот снова будет искать новые рынки
🎯 Автоматическое размещение позиций активно
📊 Мониторинг прибыли включен

⏰ <i>{datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
        """

        keyboard = [
            [InlineKeyboardButton("⏹️ Остановить торговлю", callback_data="stop")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )

    async def _cmd_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /config"""
        if not update.message:
            return

        text = f"""
⚙️ <b>Конфигурация бота</b>

💰 <b>Торговые параметры:</b>
• Размер позиции: ${config.trading.POSITION_SIZE_USD}
• Цель прибыли: {config.trading.PROFIT_TARGET_PERCENT}%
• Stop-loss: {config.trading.STOP_LOSS_PERCENT}%
• Макс. позиций: {config.trading.MAX_OPEN_POSITIONS}
• Макс. время: {config.trading.MAX_POSITION_HOURS}ч

📊 <b>Стратегия:</b>
• Режим: {config.trading.TRADING_STRATEGY}
• Сторона: {config.trading.POSITION_SIDE}
• Мин. ликвидность: ${config.trading.MIN_LIQUIDITY_USD}

🔄 <b>API:</b>
• Ротация: {'Включена' if config.trading.API_ROTATION_ENABLED else 'Отключена'}
• Задержка: {config.trading.REQUEST_DELAY_SECONDS}с

💬 <i>Для изменения параметров обновите переменные окружения в Railway</i>
        """

        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def _cmd_logs(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):  # pylint: disable=unused-argument
        """Команда /logs"""
        if not update.message:
            return

        text = """
📝 <b>Последние логи</b>

<code>
[INFO] Bot started successfully
[INFO] WebSocket connected
[INFO] Market monitor active
[INFO] No new markets found
</code>

💡 <i>Полные логи доступны в файле logs/bot.log</i>
        """

        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def _cmd_help(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):  # pylint: disable=unused-argument
        """Команда /help"""
        if not update.message:
            return

        text = """
🆘 <b>Справка по командам</b>

📊 <b>Мониторинг:</b>
/status - Статус бота и статистика
/balance - Баланс и P&L
/positions - Открытые позиции
/logs - Последние логи

🔧 <b>Управление:</b>
/stop - Остановить торговлю
/start_trading - Запустить торговлю
/config - Просмотр конфигурации

ℹ️ <b>Информация:</b>
/help - Эта справка
/start - Приветствие

🤖 <b>Автоматические уведомления:</b>
• Новые рынки
• Размещение ордеров
• Закрытие позиций с прибылью
• Ошибки и предупреждения

💡 <i>Используйте inline кнопки для быстрого доступа к функциям</i>
        """

        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def _handle_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Обработчик inline кнопок"""
        try:
            query = update.callback_query
            if not query:
                logger.warning("Callback query пустой")
                return

            await query.answer()

            data = query.data
            if not data:
                logger.warning("Callback data пустая")
                return

            logger.debug(f"Обрабатываем callback: {data}")

            # Обрабатываем callback данные напрямую без создания временного update
            if data == "status":
                await self._handle_status_callback(query)
            elif data == "balance":
                await self._handle_balance_callback(query)
            elif data == "positions":
                await self._handle_positions_callback(query)
            elif data == "config":
                await self._handle_config_callback(query)
            elif data == "stop":
                await self._handle_stop_callback(query)
            elif data == "start_trading":
                await self._handle_start_trading_callback(query)
            else:
                logger.warning(f"Неизвестная callback команда: {data}")
                
        except Exception as e:
            logger.error(f"Критическая ошибка в обработчике callback: {e}")
            try:
                if query:
                    await query.edit_message_text(
                        "❌ Произошла ошибка при обработке команды. Попробуйте еще раз.",
                        parse_mode=ParseMode.HTML
                    )
            except Exception as edit_e:
                logger.error(f"Не удалось отправить сообщение об ошибке: {edit_e}")

    async def _handle_status_callback(self, query: CallbackQuery):
        """Обработка callback для статуса"""
        try:
            logger.debug("Обработка status callback")
            stats = await self._get_current_stats()
            logger.debug(f"Получена статистика: {stats}")

            # Получаем детальный баланс
            detailed_balance = self._get_detailed_balance()
            logger.debug(f"Получен детальный баланс: {detailed_balance}")
            balance_text = ""
            
            if detailed_balance["total"] is not None:
                balance_text = f"""💰 <b>Баланс (через Polymarket API):</b>
• Свободный USDC: ${detailed_balance['free_usdc']:.2f}
• Стоимость позиций: ${detailed_balance['positions_value']:.2f}
• Общий баланс: ${detailed_balance['total']:.2f}"""
                if detailed_balance.get("proxy_wallet"):
                    balance_text += f"\n• Proxy Wallet: {detailed_balance['proxy_wallet'][:10]}..."
            else:
                fallback_balance = self._get_current_balance() or 0
                balance_text = f"💰 <b>Баланс (fallback):</b> ${fallback_balance:.2f}"

            # Получаем статус базы данных
            db_status_text = ""
            try:
                if self.trading_engine and hasattr(self.trading_engine, "client") and hasattr(self.trading_engine.client, "db_manager"):
                    db_status = self.trading_engine.client.db_manager.get_database_status()
                    db_emoji = "🗄️" if db_status["engine_type"] == "PostgreSQL" else "📁" if db_status["engine_type"] == "SQLite" else "❌"
                    db_status_text = f"\n{db_emoji} <b>База данных:</b> {db_status['engine_type']}"
                    if db_status.get("using_sqlite_fallback"):
                        db_status_text += " (fallback)"
            except Exception as db_e:
                logger.warning(f"Ошибка получения статуса БД: {db_e}")
                db_status_text = "\n❓ <b>База данных:</b> Недоступна"

            text = f"""
📊 <b>Статус бота</b>

🤖 <b>Состояние:</b> {self.bot_status}
🔄 <b>Торговля:</b> {'Включена' if stats.get('is_trading_enabled', False) else 'Отключена'}
📈 <b>Открытых позиций:</b> {stats.get('open_positions', 0)}{db_status_text}
{balance_text}

📋 <b>Сегодня:</b>
• Сделок: {stats.get('daily_trades', 0)}
• Прибыль: ${stats.get('total_profit', 0):.2f}
• Успешных: {stats.get('successful_trades', 0)}/{stats.get('total_trades', 0)}

⏰ <i>Последнее обновление: {datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
            """

            keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="status")],
                [InlineKeyboardButton("📋 Позиции", callback_data="positions")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
            )
            logger.debug("Status callback успешно обработан")
            
        except Exception as e:
            logger.error(f"Ошибка в _handle_status_callback: {e}")
            try:
                await query.edit_message_text(
                    "❌ Ошибка получения статуса. Попробуйте команду /status",
                    parse_mode=ParseMode.HTML
                )
            except Exception as edit_e:
                logger.error(f"Не удалось отправить сообщение об ошибке статуса: {edit_e}")

    async def _handle_balance_callback(self, query: CallbackQuery):
        """Обработка callback для баланса"""
        balance = self._get_current_balance()
        stats = await self._get_current_stats()
        open_positions = self._get_open_positions()

        # Рассчитываем средства в позициях
        in_positions = sum(p.get("size", 0) * p.get("price", 0) for p in open_positions)

        text = f"""
💰 <b>Баланс аккаунта</b>

💵 <b>USDC:</b> ${balance or 0:.2f}
📊 <b>В позициях:</b> ${in_positions:.2f}
💸 <b>Доступно:</b> ${(balance or 0) - in_positions:.2f}

📈 <b>P&L сегодня:</b> ${stats.get('total_profit', 0):.2f}
📊 <b>Всего сделок:</b> {stats.get('total_trades', 0)}

⏰ <i>Последнее обновление: {datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
        """

        await query.edit_message_text(text, parse_mode=ParseMode.HTML)

    async def _handle_positions_callback(self, query: CallbackQuery):
        """Обработка callback для позиций"""
        open_positions = self._get_open_positions()

        if not open_positions:
            text = f"""
📋 <b>Открытые позиции</b>

🔍 <i>Нет открытых позиций</i>

⏰ <i>Последнее обновление: {datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
            """
        else:
            text = "📋 <b>Открытые позиции</b>\n\n"

            for i, position in enumerate(
                open_positions[:5], 1
            ):  # Показываем максимум 5 позиций
                timestamp = position.get("timestamp")
                time_str = self._format_timestamp(timestamp)

                text += f"""
<b>{i}.</b> {position.get('side', 'N/A')} {position.get('size', 0):.2f}
💰 Цена: ${position.get('price', 0):.4f}
⏰ Время: {time_str}
🏷️ ID: <code>{position.get('order_id', 'N/A')[:8]}...</code>

"""

            if len(open_positions) > 5:
                text += f"<i>... и еще {len(open_positions) - 5} позиций</i>\n\n"

            text += f"⏰ <i>Последнее обновление: {datetime.utcnow().strftime('%H:%M:%S')} UTC</i>"

        keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="positions")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )

    async def _handle_config_callback(self, query: CallbackQuery):
        """Обработка callback для конфигурации"""
        text = f"""
⚙️ <b>Конфигурация бота</b>

💰 <b>Торговые параметры:</b>
• Размер позиции: ${config.trading.POSITION_SIZE_USD}
• Цель прибыли: {config.trading.PROFIT_TARGET_PERCENT}%
• Stop-loss: {config.trading.STOP_LOSS_PERCENT}%
• Макс. позиций: {config.trading.MAX_OPEN_POSITIONS}
• Макс. время: {config.trading.MAX_POSITION_HOURS}ч

📊 <b>Стратегия:</b>
• Режим: {config.trading.TRADING_STRATEGY}
• Сторона: {config.trading.POSITION_SIDE}
• Мин. ликвидность: ${config.trading.MIN_LIQUIDITY_USD}

🔄 <b>API:</b>
• Ротация: {'Включена' if config.trading.API_ROTATION_ENABLED else 'Отключена'}
• Задержка: {config.trading.REQUEST_DELAY_SECONDS}с

💬 <i>Для изменения параметров обновите переменные окружения в Railway</i>
        """

        await query.edit_message_text(text, parse_mode=ParseMode.HTML)

    async def _handle_stop_callback(self, query: CallbackQuery):
        """Обработка callback для остановки торговли"""
        if self.trading_engine:
            self.trading_engine.disable_trading()

        self.trading_enabled = False

        text = f"""
⏹️ <b>Торговля остановлена</b>

🚫 Бот больше не будет открывать новые позиции
📋 Существующие позиции остаются активными
🔄 Для возобновления используйте /start_trading

⏰ <i>{datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
        """

        keyboard = [
            [
                InlineKeyboardButton(
                    "▶️ Запустить торговлю", callback_data="start_trading"
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )

    async def _handle_start_trading_callback(self, query: CallbackQuery):
        """Обработка callback для запуска торговли"""
        if self.trading_engine:
            self.trading_engine.enable_trading()

        self.trading_enabled = True

        text = f"""
▶️ <b>Торговля запущена</b>

✅ Бот снова будет искать новые рынки
🎯 Автоматическое размещение позиций активно
📊 Мониторинг прибыли включен

⏰ <i>{datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
        """

        keyboard = [
            [InlineKeyboardButton("⏹️ Остановить торговлю", callback_data="stop")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )


# Глобальный экземпляр уведомителя
telegram_notifier = TelegramNotifier(
    bot_token=config.telegram.TELEGRAM_BOT_TOKEN,
    chat_id=config.telegram.TELEGRAM_CHAT_ID,
)
