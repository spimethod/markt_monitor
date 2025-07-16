"""Telegram bot module."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)
from telegram import CallbackQuery

from src.config.settings import config

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Класс для уведомлений в Telegram"""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.app: Optional[Application] = None
        self.bot_status = "initialized"
        self.trading_engine: Optional[Any] = None
        self.trading_enabled = True
        self._initialize_bot()

    def set_trading_engine(self, trading_engine: Any):
        """Установка торгового движка для доступа к статусу"""
        self.trading_engine = trading_engine

    def _initialize_bot(self):
        """Инициализация Telegram бота"""
        try:
            self.app = Application.builder().token(self.bot_token).build()

            # Регистрируем обработчики команд
            self.app.add_handler(CommandHandler("start", self._cmd_start))
            self.app.add_handler(CommandHandler("status", self._cmd_status))
            self.app.add_handler(CommandHandler("positions", self._cmd_positions))
            self.app.add_handler(CommandHandler("stop", self._cmd_stop_trading))
            self.app.add_handler(CommandHandler("start_trading", self._cmd_start_trading))
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

        except Exception as e:
            logger.error(f"Ошибка запуска Telegram бота: {e}")
            raise

    async def stop_bot(self):
        """Остановка Telegram бота"""
        try:
            if self.app:
                await self.app.stop()

            self.bot_status = "stopped"
            logger.info("Telegram бот остановлен")
        except Exception as e:
            logger.error(f"Ошибка остановки Telegram бота: {e}")

    async def send_message(self, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
        """Отправка сообщения в Telegram"""
        try:
            if self.app:
                await self.app.bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                )
            logger.debug(f"Сообщение отправлено в Telegram: {text[:50]}...")
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения в Telegram: {e}")

    # ===== УВЕДОМЛЕНИЯ =====

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

    async def send_error_notification(self, error_msg: str):
        """Уведомление об ошибке"""
        if not config.telegram.NOTIFY_ERRORS:
            return

        text = f"""
❌ <b>Ошибка в боте</b>

📝 <b>Описание:</b> {error_msg}

⏰ <i>{datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
        """

        keyboard = [
            [InlineKeyboardButton("📊 Статус", callback_data="status")],
            [InlineKeyboardButton("📋 Логи", callback_data="logs")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await self.send_message(text, reply_markup=reply_markup)

    async def send_websocket_fallback_notification(self):
        """Уведомление о переходе на HTTP polling"""
        text = f"""
⚠️ <b>WebSocket недоступен</b>

🔄 Переключение на HTTP polling
📊 Задержка: до 60 секунд
🔧 Попытка восстановления каждые 30 сек

⏰ <i>{datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
        """

        await self.send_message(text)

    async def send_search_summary(self, total_markets: int, suitable_markets: int, new_markets: int):
        """Сводка поиска рынков"""
        text = f"""
🔍 <b>Поиск завершен</b>

📊 Проанализировано: {total_markets} рынков
✅ Подходящих: {suitable_markets}
🆕 Новых: {new_markets}

⏰ <i>{datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
        """

        await self.send_message(text)

    # ===== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ =====

    async def _get_current_stats(self) -> Dict:
        """Получение текущей статистики"""
        if self.trading_engine:
            return {
                "is_trading_enabled": self.trading_engine.is_trading_enabled,
                "total_trades": self.trading_engine.stats.get("total_trades", 0),
                "successful_trades": self.trading_engine.stats.get("successful_trades", 0),
                "total_profit": self.trading_engine.stats.get("total_profit", 0.0),
                "open_positions": len(self._get_open_positions()),
                "daily_trades": self.trading_engine.stats.get("daily_trades", 0),
            }
        return {
            "is_trading_enabled": False,
            "total_trades": 0,
            "successful_trades": 0,
            "total_profit": 0.0,
            "open_positions": 0,
            "daily_trades": 0,
        }

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
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                return dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, AttributeError):
                return timestamp[:16] if len(timestamp) > 16 else timestamp
        return "N/A"

    # ===== ОБРАБОТЧИКИ КОМАНД =====

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        if not update.message:
            return

        text = """
👋 <b>Добро пожаловать в Polymarket Trading Bot!</b>

🤖 Этот бот автоматически торгует на Polymarket, покупая позиции NO на новых рынках.

📋 <b>Доступные команды:</b>
/status - Статус бота
/positions - Открытые позиции
/stop - Остановить торговлю
/start_trading - Запустить торговлю
/config - Конфигурация
/logs - Последние логи

🚀 Бот готов к работе!
        """

        keyboard = [
            [InlineKeyboardButton("📊 Статус", callback_data="status")],
            [InlineKeyboardButton("📋 Позиции", callback_data="positions")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="config")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /status"""
        if not update.message:
            return

        stats = await self._get_current_stats()

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

    async def _cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /positions"""
        if not update.message:
            return

        open_positions = self._get_open_positions()

        if not open_positions:
            text = f"📋 <b>Открытых позиций нет</b>\n\n⏰ <i>Проверено: {datetime.utcnow().strftime('%H:%M:%S')}</i>"
            keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="positions")],
                [InlineKeyboardButton("📊 Статус", callback_data="status")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
            )
            return

        text = f"📋 <b>Открытые позиции</b> ({len(open_positions)})\n\n"

        for pos in open_positions:
            created_at = self._format_timestamp(pos.get("created_at"))
            pnl = pos.get("pnl", 0.0)
            pnl_emoji = "📈" if pnl > 0 else "📉" if pnl < 0 else "📊"

            text += f"""
🏷️ <b>ID:</b> <code>{pos.get('id', 'N/A')[:10]}...</code>
💱 <b>Токен:</b> <code>{pos.get('token_id', 'N/A')[:10]}...</code>
📊 <b>Размер:</b> {pos.get('size', 0):.2f}
💰 <b>Цена входа:</b> ${pos.get('entry_price', 0):.4f}
{pnl_emoji} <b>PnL:</b> ${pnl:.2f} ({(pnl / (pos.get('size', 1) * pos.get('entry_price', 1)) * 100):.1f}%)
🕒 <b>Открыта:</b> {created_at}
            """
            text += "\n" + "-" * 20 + "\n"

        text += f"\n⏰ <i>{datetime.utcnow().strftime('%H:%M:%S')} UTC</i>"

        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data="positions")],
            [InlineKeyboardButton("📊 Статус", callback_data="status")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )

    async def _cmd_stop_trading(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            [InlineKeyboardButton("▶️ Запустить торговлю", callback_data="start_trading")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )

    async def _cmd_start_trading(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    async def _cmd_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /logs"""
        if not update.message:
            return

        text = """
📝 <b>Последние логи</b>

💬 <i>Функция логов в разработке. Пожалуйста, проверьте файл logs/bot.log вручную.</i>
        """

        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        if not update.message:
            return

        text = """
📚 <b>Справка по командам</b>

/start - Запуск бота
/status - Статус бота
/positions - Открытые позиции
/stop - Остановить торговлю
/start_trading - Запустить торговлю
/config - Конфигурация
/logs - Последние логи
/help - Эта справка

💡 <i>Все команды доступны через меню или inline-кнопки</i>
        """

        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    # ===== ОБРАБОТЧИКИ CALLBACK =====

    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка callback queries от inline кнопок"""
        query = update.callback_query
        if not query:
            return

        await query.answer()

        if query.data == "status":
            await self._handle_status_callback(query)
        elif query.data == "positions":
            await self._handle_positions_callback(query)
        elif query.data == "config":
            await self._handle_config_callback(query)
        elif query.data == "stop":
            await self._handle_stop_callback(query)
        elif query.data == "start_trading":
            await self._handle_start_trading_callback(query)
        elif query.data == "logs":
            await self._handle_logs_callback(query)

    async def _handle_status_callback(self, query: CallbackQuery):
        """Обработка callback для статуса"""
        stats = await self._get_current_stats()

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

    async def _handle_positions_callback(self, query: CallbackQuery):
        """Обработка callback для позиций"""
        open_positions = self._get_open_positions()

        if not open_positions:
            text = f"📋 <b>Открытых позиций нет</b>\n\n⏰ <i>Проверено: {datetime.utcnow().strftime('%H:%M:%S')}</i>"
            keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="positions")],
                [InlineKeyboardButton("📊 Статус", callback_data="status")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
            )
            return

        text = f"📋 <b>Открытые позиции</b> ({len(open_positions)})\n\n"

        for pos in open_positions:
            created_at = self._format_timestamp(pos.get("created_at"))
            pnl = pos.get("pnl", 0.0)
            pnl_emoji = "📈" if pnl > 0 else "📉" if pnl < 0 else "📊"

            text += f"""
🏷️ <b>ID:</b> <code>{pos.get('id', 'N/A')[:10]}...</code>
💱 <b>Токен:</b> <code>{pos.get('token_id', 'N/A')[:10]}...</code>
📊 <b>Размер:</b> {pos.get('size', 0):.2f}
💰 <b>Цена входа:</b> ${pos.get('entry_price', 0):.4f}
{pnl_emoji} <b>PnL:</b> ${pnl:.2f} ({(pnl / (pos.get('size', 1) * pos.get('entry_price', 1)) * 100):.1f}%)
🕒 <b>Открыта:</b> {created_at}
            """
            text += "\n" + "-" * 20 + "\n"

        text += f"\n⏰ <i>{datetime.utcnow().strftime('%H:%M:%S')} UTC</i>"

        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data="positions")],
            [InlineKeyboardButton("📊 Статус", callback_data="status")],
        ]
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
            [InlineKeyboardButton("▶️ Запустить торговлю", callback_data="start_trading")]
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

    async def _handle_logs_callback(self, query: CallbackQuery):
        """Обработка callback для логов"""
        text = """
📝 <b>Последние логи</b>

💬 <i>Функция логов в разработке. Пожалуйста, проверьте файл logs/bot.log вручную.</i>
        """

        await query.edit_message_text(text, parse_mode=ParseMode.HTML)


# Глобальный экземпляр
telegram_notifier = TelegramNotifier(
    bot_token=config.telegram.TELEGRAM_BOT_TOKEN,
    chat_id=config.telegram.TELEGRAM_CHAT_ID,
)
