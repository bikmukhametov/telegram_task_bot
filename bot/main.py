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
from keyboards import get_main_menu_keyboard

app_logger = logging.getLogger('app')
user_logger = logging.getLogger('user_actions')

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

async def on_startup_notify(bot: Bot, pool):
    app_logger.info("Отправка уведомлений пользователям об возобновлении работы бота...")
    async with pool.acquire() as conn:
        users = await conn.fetch('SELECT user_id, role, full_name FROM users')
        for user in users:
            try:
                keyboard = get_main_menu_keyboard(user['role'])
                await bot.send_message(
                    user['user_id'],
                    "Возникли временные технические неполадки в работе нашего Telegram-бота. " +
                    "Сейчас все проблемы устранены, и он снова полностью функционирует. " +
                    "Приносим извинения за доставленные неудобства!",
                    reply_markup=keyboard
                )
                user_logger.info(f"Пользователю {user['user_id']} ({user['full_name']}) отправлено обновленное меню.")
            except Exception as e:
                app_logger.error(f"Не удалось отправить сообщение пользователю {user['user_id']}: {e}")
    app_logger.info("Отправка уведомлений завершена.")

async def on_shutdown_notify(bot: Bot, pool):
    app_logger.info("Отправка уведомлений пользователям о выключении бота...")
    async with pool.acquire() as conn:
        users = await conn.fetch('SELECT user_id FROM users')
        for user in users:
            try:
                await bot.send_message(
                    user['user_id'],
                    "Бот временно остановлен на техническое обслуживание. Мы скоро вернемся!"
                )
            except Exception as e:
                app_logger.error(f"Не удалось отправить сообщение о выключении пользователю {user['user_id']}: {e}")
    app_logger.info("Отправка уведомлений о выключении завершена.")

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

    async def on_shutdown(bot: Bot, pool: asyncpg.Pool):
        app_logger.info("Бот останавливается...")
        await on_shutdown_notify(bot, pool)
        await pool.close()
        app_logger.info("Пул подключений к БД закрыт")

    dp.shutdown.register(on_shutdown)

    try:
        await on_startup_notify(bot, pool)
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