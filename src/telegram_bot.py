"""Telegram bot module."""

import asyncio
import itertools
import logging
import pathlib
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

# Константы для логов
LOG_PATHS = [
    pathlib.Path("logs/bot.log"),
    pathlib.Path("/app/logs/bot.log"),  # Railway
    pathlib.Path("./logs/bot.log"),
    pathlib.Path("../logs/bot.log"),
]
TAIL_LINES = 30  # количество строк для отправки
MAX_MESSAGE_LENGTH = 4000  # максимальная длина сообщения в Telegram


def find_log_file() -> pathlib.Path:
    """Находит файл логов среди возможных путей"""
    for log_path in LOG_PATHS:
        if log_path.exists():
            return log_path
    return LOG_PATHS[0]  # Возвращаем первый путь как fallback

def tail_log(path: pathlib.Path, n: int) -> str:
    """Читает последние n строк из файла лога"""
    try:
        if not path.exists():
            return "Файл логов не найден"
        
        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
            if not lines:
            return "Лог пуст"
            
            # Берем последние n строк
            last_lines = lines[-n:] if len(lines) > n else lines
        return "".join(last_lines)
    except Exception as e:
        return f"Ошибка чтения логов: {e}"


def escape_html(text: str) -> str:
    """Экранирует HTML символы для безопасного отображения в Telegram"""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


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
            
            # Новые команды для торговли
            self.app.add_handler(CommandHandler("orders", self._cmd_orders))
            self.app.add_handler(CommandHandler("cancel", self._cmd_cancel_order))
            self.app.add_handler(CommandHandler("trade", self._cmd_trade))

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

    def _get_logs_content(self) -> str:
        """Получение содержимого логов"""
        try:
            log_path = find_log_file()
            
            # Проверяем существование файла
            if not log_path.exists():
            return f"Файл логов не найден: {log_path.absolute()}"
            
            # Проверяем размер файла
            file_size = log_path.stat().st_size
            if file_size == 0:
            return "Файл логов пуст"
            
            content = tail_log(log_path, TAIL_LINES)
            if not content or content.strip() == "":
            return f"Лог пуст или недоступен. Размер файла: {file_size} байт"
            
            # Экранируем HTML символы
            escaped_content = escape_html(content)
            
            # Ограничиваем длину сообщения
            if len(escaped_content) > MAX_MESSAGE_LENGTH:
                escaped_content = escaped_content[-MAX_MESSAGE_LENGTH:] + "\n\n... (обрезано)"
            
            return escaped_content
        except Exception as e:
            log_path = find_log_file()
            return f"Ошибка чтения логов: {e}\nПуть: {log_path.absolute()}"

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

        try:
            logger.info("Команда /logs выполнена")
            content = self._get_logs_content()
            logger.info(f"Получено содержимое логов длиной: {len(content)} символов")
            
        text = f"""
📝 <b>Последние {TAIL_LINES} строк журнала</b>

<code>{content}</code>

⏰ <i>Обновлено: {datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
            """

        keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="logs")],
                [InlineKeyboardButton("📊 Статус", callback_data="status")],
            ]
        reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            logger.info("Команда /logs успешно выполнена")
            
        except Exception as e:
            logger.error(f"Ошибка в команде /logs: {e}")
            error_text = f"""
❌ <b>Ошибка получения логов</b>

📝 <b>Описание:</b> {str(e)}

⏰ <i>{datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
        """
            await update.message.reply_text(error_text, parse_mode=ParseMode.HTML)

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        if not update.message:
            return

        text = """
📚 <b>Справка по командам</b>

📋 <b>Основные команды:</b>
/start - Запуск бота
/status - Статус бота
/positions - Открытые позиции
/stop - Остановить торговлю
/start_trading - Запустить торговлю
/config - Конфигурация
/logs - Последние логи
/help - Эта справка

📈 <b>Торговые команды:</b>
/orders - Активные ордера
/cancel [order_id] - Отменить ордер
/trade [market_id] [side] [size] [price] - Ручная торговля

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
        try:
            logger.info("Callback /logs выполнена")
            content = self._get_logs_content()
            logger.info(f"Получено содержимое логов длиной: {len(content)} символов")
            
        text = f"""
📝 <b>Последние {TAIL_LINES} строк журнала</b>

<code>{content}</code>

⏰ <i>Обновлено: {datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
            """

        keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="logs")],
                [InlineKeyboardButton("📊 Статус", callback_data="status")],
            ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            logger.info("Callback /logs успешно выполнена")
            
        except Exception as e:
            logger.error(f"Ошибка в callback /logs: {e}")
            error_text = f"""
❌ <b>Ошибка получения логов</b>

📝 <b>Описание:</b> {str(e)}

⏰ <i>{datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
            """
        await query.edit_message_text(error_text, parse_mode=ParseMode.HTML)

    async def _cmd_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /orders - показывает активные ордера"""
        if not update.message:
            return
            
        try:
            if not self.trading_engine or not self.trading_engine.client:
                await update.message.reply_text("❌ Торговый движок недоступен")
            return

            orders = await self.trading_engine.client.get_my_orders()
            
            if not orders:
                await update.message.reply_text("📋 Нет активных ордеров")
            return

            text = f"📋 <b>Активные ордера ({len(orders)}):</b>\n\n"
            
            for i, order in enumerate(orders[:10], 1):  # Показываем первые 10
                side_emoji = "🟢" if order.get("side") == "BUY" else "🔴"
                text += f"{i}. {side_emoji} <b>{order.get('side', 'N/A')}</b>\n"
                text += f"   🏷️ ID: <code>{order.get('order_id', 'N/A')}</code>\n"
                text += f"   💱 Токен: <code>{order.get('asset_id', 'N/A')[:20]}...</code>\n"
                text += f"   📊 Размер: {order.get('size', 0):.2f}\n"
                text += f"   💰 Цена: ${order.get('price', 0):.4f}\n"
                text += f"   📅 Истекает: {self._format_timestamp(order.get('expires'))}\n\n"

            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
            
        except Exception as e:
            logger.error(f"Ошибка получения ордеров: {e}")
            await update.message.reply_text(f"❌ Ошибка получения ордеров: {str(e)}")

    async def _cmd_cancel_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /cancel [order_id] - отменяет ордер"""
        if not update.message:
            return
            
        try:
            if not context.args or len(context.args) == 0:
                await update.message.reply_text("❌ Укажите ID ордера: /cancel [order_id]")
            return

            order_id = context.args[0]
            
            if not self.trading_engine or not self.trading_engine.client:
                await update.message.reply_text("❌ Торговый движок недоступен")
            return

            success = await self.trading_engine.client.cancel_order(order_id)
            
            if success:
                await update.message.reply_text(f"✅ Ордер {order_id} успешно отменен")
            else:
                await update.message.reply_text(f"❌ Не удалось отменить ордер {order_id}")
                
        except Exception as e:
            logger.error(f"Ошибка отмены ордера: {e}")
            await update.message.reply_text(f"❌ Ошибка отмены ордера: {str(e)}")

    async def _cmd_trade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /trade [market_id] [side] [size] [price] - ручная торговля"""
        if not update.message:
            return
            
        try:
            if not context.args or len(context.args) < 4:
                await update.message.reply_text(
                    "❌ Недостаточно параметров: /trade [market_id] [side] [size] [price]\n"
                    "Пример: /trade 123 BUY 100 0.5"
                )
            return

            market_id, side, size_str, price_str = context.args[:4]
            
            try:
                size = float(size_str)
                price = float(price_str)
            except ValueError:
                await update.message.reply_text("❌ Размер и цена должны быть числами")
            return

            if side.upper() not in ["BUY", "SELL"]:
                await update.message.reply_text("❌ Сторона должна быть BUY или SELL")
            return

            if not self.trading_engine or not self.trading_engine.client:
                await update.message.reply_text("❌ Торговый движок недоступен")
            return

            # Получаем данные рынка
            markets = self.trading_engine.client.get_markets()
            market_data = None
            
            for market in markets:
                if (market.get("question_id") == market_id or 
                    market.get("condition_id") == market_id or 
                    market.get("market_slug") == market_id):
                    market_data = market
                    break

            if not market_data:
                await update.message.reply_text(f"❌ Рынок {market_id} не найден")
            return

            # Получаем token_id для нужной стороны
            token_id = None
            for token in market_data.get("tokens", []):
                if side.upper() == "BUY" and "YES" in token.get("outcome", ""):
                    token_id = token.get("token_id")
                    break
                elif side.upper() == "SELL" and "NO" in token.get("outcome", ""):
                    token_id = token.get("token_id")
                    break

            if not token_id:
                await update.message.reply_text(f"❌ Не удалось найти токен для {side}")
            return

            # Размещаем ордер
            order_result = await self.trading_engine.client.place_order(
                token_id, side.upper(), size, price, market_data
            )

            if order_result:
                await update.message.reply_text(
                    f"✅ Ордер размещен!\n"
                    f"🏷️ ID: {order_result.get('order_id', 'N/A')}\n"
                    f"💱 {side.upper()} {size} по цене ${price:.4f}"
                )
            else:
                await update.message.reply_text("❌ Не удалось разместить ордер")
                
        except Exception as e:
            logger.error(f"Ошибка ручной торговли: {e}")
            await update.message.reply_text(f"❌ Ошибка торговли: {str(e)}")


# Глобальный экземпляр
telegram_notifier = TelegramNotifier(
    bot_token=config.telegram.TELEGRAM_BOT_TOKEN,
    chat_id=config.telegram.TELEGRAM_CHAT_ID,
)
