import asyncpg
from datetime import datetime
import logging

app_logger = logging.getLogger('app')

class User:
    def __init__(self, user_id: int, full_name: str, role: str = 'user', organization_id: int = None):
        self.user_id = user_id
        self.full_name = full_name
        self.role = role
        self.organization_id = organization_id

class Organization:
    def __init__(self, org_id: int, name: str):
        self.org_id = org_id
        self.name = name

class Task:
    def __init__(self, task_id: int, title: str, description: str, employee_id: int, manager_id: int, organization_id: int, status: str = 'new', created_at: datetime = None):
        self.task_id = task_id
        self.title = title
        self.description = description
        self.employee_id = employee_id
        self.manager_id = manager_id
        self.organization_id = organization_id
        self.status = status
        self.created_at = created_at if created_at is not None else datetime.now()

async def create_tables(conn: asyncpg.Connection):
    try:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS organizations (
                org_id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL
            );
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                full_name VARCHAR(255) NOT NULL,
                role VARCHAR(50) DEFAULT 'user',
                organization_id INTEGER REFERENCES organizations(org_id) ON DELETE SET NULL
            );
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                task_id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                employee_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                manager_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                organization_id INTEGER REFERENCES organizations(org_id) ON DELETE CASCADE,
                status VARCHAR(50) DEFAULT 'new',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        app_logger.info("Таблицы в базе данных созданы успешно")
    except Exception as e:
        app_logger.error(f"Ошибка при создании таблиц в базе данных: {e}")
        raise