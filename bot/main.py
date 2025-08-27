import asyncio
import logging
from logging.handlers import RotatingFileHandler
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
import asyncpg
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from db import create_db_pool, init_db
from handlers import start_handlers, admin_handlers, manager_handlers, employee_handlers

def setup_logging():
    if not os.path.exists('logs'):
        os.makedirs('logs')

    logger = logging.getLogger('app')
    logger.setLevel(logging.INFO)

    user_logger = logging.getLogger('user_actions')
    user_logger.setLevel(logging.INFO)

    # Обработчик для app.log
    app_handler = RotatingFileHandler('logs/app.log', maxBytes=1024*1024, backupCount=10, encoding='utf-8')
    app_handler.setLevel(logging.INFO)
    app_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    app_handler.setFormatter(app_formatter)

    # Обработчик для user_actions.log
    user_handler = RotatingFileHandler('logs/user_actions.log', maxBytes=1024*1024, backupCount=10, encoding='utf-8')
    user_handler.setLevel(logging.INFO)
    user_formatter = logging.Formatter('%(asctime)s - %(message)s')
    user_handler.setFormatter(user_formatter)

    # Консольный обработчик для app
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(app_formatter)
    logger.addHandler(console_handler)

    # Добавляем обработчики к логгерам
    logger.addHandler(app_handler)
    user_logger.addHandler(user_handler)

    return logger, user_logger

async def main():
    app_logger, user_logger = setup_logging()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start_handlers.router)
    dp.include_router(admin_handlers.router)
    dp.include_router(manager_handlers.router)
    dp.include_router(employee_handlers.router)

    pool = await create_db_pool()
    await init_db(pool)

    dp['pool'] = pool

    async def on_shutdown(bot: Bot):
        app_logger.info("Бот останавливается...")
        await pool.close()
        app_logger.info("Пул подключений к БД закрыт")

    dp.shutdown.register(on_shutdown)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        app_logger.info("Бот запущен")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        app_logger.info("Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.getLogger('app').info("Бот остановлен вручную")