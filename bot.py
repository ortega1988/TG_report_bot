import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import TelegramObject
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode

from config import BOT_TOKEN, DB_PATH, WEBAPP_URL, WEBAPP_PORT, TELEGRAM_LOCAL, TELEGRAM_API_URL
from app.database.connection import Database
from app.database.repository import BugReportRepository
from app.handlers import webapp_handler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DatabaseMiddleware(BaseMiddleware):
    """Мидлварь для передачи репозитория БД в обработчики"""

    def __init__(self, report_repo: BugReportRepository):
        self.report_repo = report_repo

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        data["report_repo"] = self.report_repo
        return await handler(event, data)


async def main():
    """Главная функция запуска бота"""
    db = Database(DB_PATH)

    await db.connect()
    logger.info("База данных подключена")

    report_repo = BugReportRepository(db)

    if TELEGRAM_LOCAL:
        local_server = TelegramAPIServer.from_base(TELEGRAM_API_URL, is_local=True)
        session = AiohttpSession(api=local_server)
        logger.info(f"Используется локальный Telegram Bot API: {TELEGRAM_API_URL}")
    else:
        session = None

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session
    )

    bot_info = await bot.get_me()
    logger.info(f"Бот @{bot_info.username} запущен (id={bot_info.id})")

    dp = Dispatcher(storage=MemoryStorage())

    db_middleware = DatabaseMiddleware(report_repo)
    dp.message.middleware(db_middleware)
    dp.callback_query.middleware(db_middleware)

    webapp_handler.set_bot_info(bot_info)
    dp.include_router(webapp_handler.router)

    webapp_runner = None
    if WEBAPP_URL:
        from webapp.server import start_webapp
        webapp_runner = await start_webapp(
            bot=bot,
            report_repo=report_repo,
            bot_token=BOT_TOKEN,
            port=WEBAPP_PORT
        )
        logger.info(f"Web App сервер запущен на порту {WEBAPP_PORT}")
    else:
        logger.warning("WEBAPP_URL не установлен - Web App отключён")

    logger.info("Запуск polling...")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        if webapp_runner:
            await webapp_runner.cleanup()
            logger.info("Web App сервер остановлен")
        await db.disconnect()
        logger.info("База данных отключена")
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
