import asyncpg
from config import DB_HOST, DB_NAME, DB_USER, DB_PASSWORD
from models import create_tables
import logging

app_logger = logging.getLogger('app')

async def create_db_pool():
    try:
        pool = await asyncpg.create_pool(
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            database=DB_NAME
        )
        app_logger.info("Пу подключений к базе данных создан успешно")
        return pool
    except Exception as e:
        app_logger.error(f"Ошибка при создании пула подключений к базе данных: {e}")
        raise

async def init_db(pool):
    try:
        async with pool.acquire() as conn:
            await create_tables(conn)
        app_logger.info("База данных инициализирована успешно")
    except Exception as e:
        app_logger.error(f"Ошибка при инициализации базы данных: {e}")
        raise