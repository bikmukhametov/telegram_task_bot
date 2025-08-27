from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
import asyncpg
import logging

from keyboards import get_main_menu_keyboard, get_confirm_assign_employee_keyboard, get_keyboard_with_back_button, get_users_for_assign_employee_keyboard, get_employees_for_remove_keyboard, get_employees_for_assign_task_keyboard
from states import ManagerStates
from config import ADMIN_ID
from instructions import EMPLOYEE_INSTRUCTIONS
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

router = Router()

app_logger = logging.getLogger('app')
user_logger = logging.getLogger('user_actions')

status_emojis = {
    'new': '🆕',
    'accepted': '✅',
    'completed': '🎉',
    'rejected': '❌'
}

status_display_map = {
    'new': 'Новая',
    'accepted': 'Принята',
    'completed': 'Выполнена',
    'rejected': 'Отказана'
}

async def is_manager(user_id: int, pool: asyncpg.Pool) -> bool:
    async with pool.acquire() as conn:
        user = await conn.fetchrow('SELECT role FROM users WHERE user_id = $1', user_id)
        return user and user['role'] == 'manager'

async def send_task_notification(bot: Bot, user_id: int, message_text: str, reply_markup = None, parse_mode: str = 'HTML'):
    try:
        await bot.send_message(user_id, message_text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramForbiddenError:
        app_logger.warning(f"Target user {user_id} blocked the bot.")
    except TelegramBadRequest as e:
        app_logger.error(f"Failed to send message to user {user_id}: {e}")

async def get_manager_tasks_by_status(manager_id: int, pool: asyncpg.Pool, status: str = None):
    async with pool.acquire() as conn:
        if status:
            if status in ['completed', 'rejected']:
                tasks = await conn.fetch('''
                    SELECT t.task_id, t.title, t.description, t.status, u.full_name as employee_name, u2.full_name as manager_name
                    FROM tasks t
                    JOIN users u ON t.employee_id = u.user_id
                    JOIN users u2 ON t.manager_id = u2.user_id
                    WHERE t.manager_id = $1 AND t.status = $2
                    ORDER BY t.created_at DESC
                    LIMIT 20
                ''', manager_id, status)
            else:
                tasks = await conn.fetch('''
                    SELECT t.task_id, t.title, t.description, t.status, u.full_name as employee_name, u2.full_name as manager_name
                    FROM tasks t
                    JOIN users u ON t.employee_id = u.user_id
                    JOIN users u2 ON t.manager_id = u2.user_id
                    WHERE t.manager_id = $1 AND t.status = $2
                    ORDER BY t.created_at DESC
                ''', manager_id, status)
        else:
            tasks = await conn.fetch('''
                SELECT t.task_id, t.title, t.description, t.status, u.full_name as employee_name, u2.full_name as manager_name
                FROM tasks t
                JOIN users u ON t.employee_id = u.user_id
                JOIN users u2 ON t.manager_id = u2.user_id
                WHERE t.manager_id = $1
                ORDER BY t.created_at DESC
            ''', manager_id)
        return tasks

async def format_manager_tasks_response(tasks, status_filter: str = None):
    if tasks:
        response = "Задачи вашей организации:\n"
        for task in tasks:
            display_status = status_display_map.get(task['status'], task['status'])
            emoji = status_emojis.get(task['status'], '')
            response += (f"---------------------------\n"
                         f"ID: {task['task_id']}\n"
                         f"Название: {task['title']}\n"
                         f"Описание: {task['description']}\n"
                         f"Статус: {emoji} {display_status}\n"
                         f"Сотрудник: {task['employee_name']}\n")
        
        if status_filter in ['completed', 'rejected']:
            response += "\n<b>(Отображены только 20 последних задач)</b>"
    else:
        response = "У вашей организации пока нет задач."
    return response


@router.message(F.text == "Просмотр сотрудников")
async def view_employees(message: Message, pool: asyncpg.Pool):
    if not await is_manager(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        app_logger.warning(f"Пользователь {message.from_user.id} попытался просмотреть сотрудников без прав менеджера")
        return

    user_id = message.from_user.id
    async with pool.acquire() as conn:
        manager_org = await conn.fetchrow('SELECT organization_id FROM users WHERE user_id = $1', user_id)
        if not manager_org or not manager_org['organization_id']:
            await message.answer("Вы не привязаны ни к одной организации как менеджер.")
            app_logger.warning(f"Менеджер {user_id} не привязан к организации при попытке просмотреть сотрудников")
            return

        employees = await conn.fetch('SELECT user_id, full_name, role FROM users WHERE organization_id = $1 AND role = $2',
                                     manager_org['organization_id'], 'employee')
        if employees:
            response = "Список сотрудников вашей организации:\n"
            for emp in employees:
                response += f"- ID: {emp['user_id']}, ФИО: {emp['full_name']}\n"
            await message.answer(response)
            user_logger.info(f"Менеджер {user_id} просмотрел список сотрудников")
        else:
            await message.answer("В вашей организации пока нет сотрудников.")
            user_logger.info(f"Менеджер {user_id} просмотрел список сотрудников (пусто)")

@router.message(F.text == "Назначить сотрудника")
async def assign_employee_prompt(message: Message, state: FSMContext, pool: asyncpg.Pool):
    if not await is_manager(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        app_logger.warning(f"Пользователь {message.from_user.id} попытался назначить сотрудника без прав менеджера")
        return

    user_id = message.from_user.id
    async with pool.acquire() as conn:
        manager_org = await conn.fetchrow('SELECT organization_id FROM users WHERE user_id = $1', user_id)
        if not manager_org or not manager_org['organization_id']:
            await message.answer("Вы не привязаны ни к одной организации как менеджер.")
            app_logger.warning(f"Менеджер {user_id} не привязан к организации при попытке назначить сотрудника")
            return

        users = await conn.fetch('SELECT user_id, full_name, role FROM users WHERE role = $1 AND organization_id IS NULL', 'user')
        if users:
            await message.answer("Выберите пользователя, которого хотите назначить сотрудником:",
                                 reply_markup=get_users_for_assign_employee_keyboard(users))
            await state.set_state(ManagerStates.waiting_for_employee_id)
            user_logger.info(f"Менеджер {user_id} начал назначение сотрудника")
        else:
            await message.answer("Нет доступных пользователей для назначения сотрудником.",
                                 reply_markup=get_main_menu_keyboard('manager'))
            user_logger.info(f"Менеджер {user_id} попытался назначить сотрудника (нет пользователей)")

@router.callback_query(F.data.startswith("select_user_assign_employee_"))
async def select_user_to_assign_employee(callback_query: CallbackQuery, state: FSMContext, pool: asyncpg.Pool, bot: Bot):
    user_id = int(callback_query.data.split('_')[4])
    await callback_query.message.edit_reply_markup(reply_markup=None)

    async with pool.acquire() as conn:
        user = await conn.fetchrow('SELECT full_name, role FROM users WHERE user_id = $1', user_id)
        if user:
            manager_id = callback_query.from_user.id
            manager_org = await conn.fetchval('SELECT organization_id FROM users WHERE user_id = $1', manager_id)

            if manager_org:
                await conn.execute('UPDATE users SET role = $1, organization_id = $2 WHERE user_id = $3',
                                   'employee', manager_org, user_id)
                await callback_query.message.answer(f"Пользователь '<b>{user['full_name']}</b>' назначен сотрудником "
                                                     f"в вашей организации.",
                                                     reply_markup=get_main_menu_keyboard('manager'), parse_mode='HTML')
                await state.clear()
                user_logger.info(f"Менеджер {manager_id} назначил пользователя {user_id} ({user['full_name']}) сотрудником")

                try:
                    await bot.send_message(user_id, EMPLOYEE_INSTRUCTIONS, parse_mode='HTML')
                    await bot.send_message(user_id, "Ваше главное меню:", reply_markup=get_main_menu_keyboard('employee'))
                    user_logger.info(f"Отправлены инструкции новому сотруднику {user_id}")
                except TelegramForbiddenError:
                    app_logger.warning(f"Target user {user_id} blocked the bot.")
                except TelegramBadRequest as e:
                    app_logger.error(f"Failed to send message to user {user_id}: {e}")
            else:
                await callback_query.message.answer("Вы не привязаны ни к одной организации. Невозможно назначить сотрудника.",
                                                     reply_markup=get_main_menu_keyboard('manager'))
                await state.clear()
                app_logger.warning(f"Менеджер {manager_id} не привязан к организации при назначении сотрудника")
        else:
            await callback_query.message.answer("Пользователь с таким User ID не найден. Пожалуйста, выберите корректного пользователя.",
                                                 reply_markup=get_main_menu_keyboard('manager'))
            await state.clear()
            app_logger.warning(f"Пользователь {user_id} не найден при назначении сотрудника")
    await callback_query.answer()


@router.message(F.text == "Удалить сотрудника")
async def remove_employee_prompt(message: Message, state: FSMContext, pool: asyncpg.Pool):
    if not await is_manager(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        app_logger.warning(f"Пользователь {message.from_user.id} попытался удалить сотрудника без прав менеджера")
        return

    manager_id = message.from_user.id
    async with pool.acquire() as conn:
        manager_org_id = await conn.fetchval('SELECT organization_id FROM users WHERE user_id = $1', manager_id)
        if not manager_org_id:
            await message.answer("Вы не привязаны ни к одной организации. Невозможно удалить сотрудника.",
                                 reply_markup=get_main_menu_keyboard('manager'))
            app_logger.warning(f"Менеджер {manager_id} не привязан к организации при попытке удалить сотрудника")
            return

        employees = await conn.fetch('SELECT user_id, full_name FROM users WHERE organization_id = $1 AND role = $2',
                                     manager_org_id, 'employee')
        if employees:
            await message.answer("Выберите сотрудника, которого хотите удалить:",
                                 reply_markup=get_employees_for_remove_keyboard(employees))
            await state.set_state(ManagerStates.waiting_for_employee_id_to_remove)
            user_logger.info(f"Менеджер {manager_id} начал удаление сотрудника")
        else:
            await message.answer("В вашей организации нет сотрудников для удаления.",
                                 reply_markup=get_main_menu_keyboard('manager'))
            user_logger.info(f"Менеджер {manager_id} попытался удалить сотрудника (нет сотрудников)")

@router.callback_query(F.data.startswith("select_employee_remove_"))
async def select_employee_to_remove(callback_query: CallbackQuery, state: FSMContext, pool: asyncpg.Pool, bot: Bot):
    user_id = int(callback_query.data.split('_')[3])
    await callback_query.message.edit_reply_markup(reply_markup=None)

    async with pool.acquire() as conn:
        employee = await conn.fetchrow('SELECT full_name FROM users WHERE user_id = $1 AND role = $2', user_id, 'employee')
        if employee:
            await conn.execute('UPDATE users SET role = $1, organization_id = NULL WHERE user_id = $2',
                               'user', user_id)
            await callback_query.message.answer(f"Сотрудник '<b>{employee['full_name']}</b>' успешно удален из вашей организации и стал обычным пользователем.",
                                                 reply_markup=get_main_menu_keyboard('manager'), parse_mode='HTML')
            await state.clear()
            user_logger.info(f"Менеджер {callback_query.from_user.id} удалил сотрудника {user_id} ({employee['full_name']})")

            try:
                await bot.send_message(user_id, f"<b>Уведомление:</b> Ваша роль была изменена на <b>Пользователь</b>. Вы больше не являетесь сотрудником.", parse_mode='HTML')
                await bot.send_message(user_id, "Ваше главное меню:", reply_markup=get_main_menu_keyboard('user'))
                user_logger.info(f"Отправлено уведомление пользователю {user_id} об изменении роли")
            except TelegramForbiddenError:
                app_logger.warning(f"Target user {user_id} blocked the bot.")
            except TelegramBadRequest as e:
                app_logger.error(f"Failed to send message to user {user_id}: {e}")
        else:
            await callback_query.message.answer("Пользователь с таким User ID не является сотрудником или не найден. Пожалуйста, выберите корректного сотрудника.",
                                                 reply_markup=get_main_menu_keyboard('manager'))
            await state.clear()
            app_logger.warning(f"Пользователь {user_id} не найден или не является сотрудником при удалении")
    await callback_query.answer()


@router.message(F.text == "Назначить задачу")
async def assign_task_prompt(message: Message, state: FSMContext, pool: asyncpg.Pool):
    if not await is_manager(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        app_logger.warning(f"Пользователь {message.from_user.id} попытался назначить задачу без прав менеджера")
        return

    manager_id = message.from_user.id
    async with pool.acquire() as conn:
        manager_org_id = await conn.fetchval('SELECT organization_id FROM users WHERE user_id = $1', manager_id)
        if not manager_org_id:
            await message.answer("Вы не привязаны ни к одной организации. Невозможно назначить задачу.",
                                 reply_markup=get_main_menu_keyboard('manager'))
            app_logger.warning(f"Менеджер {manager_id} не привязан к организации при попытке назначить задачу")
            return

        employees = await conn.fetch('SELECT user_id, full_name FROM users WHERE organization_id = $1 AND role = $2',
                                     manager_org_id, 'employee')
        if employees:
            await message.answer("Выберите сотрудника, которому хотите назначить задачу:",
                                 reply_markup=get_employees_for_assign_task_keyboard(employees))
            await state.set_state(ManagerStates.waiting_for_employee_id_to_assign_task)
            user_logger.info(f"Менеджер {manager_id} начал назначение задачи")
        else:
            await message.answer("В вашей организации нет сотрудников, которым можно назначить задачу.",
                                 reply_markup=get_main_menu_keyboard('manager'))
            user_logger.info(f"Менеджер {manager_id} попытался назначить задачу (нет сотрудников)")

@router.callback_query(F.data.startswith("select_employee_assign_task_"))
async def select_employee_to_assign_task(callback_query: CallbackQuery, state: FSMContext, pool: asyncpg.Pool):
    employee_id = int(callback_query.data.split('_')[4])
    await callback_query.message.edit_reply_markup(reply_markup=None)

    async with pool.acquire() as conn:
        employee = await conn.fetchrow('SELECT full_name FROM users WHERE user_id = $1 AND role = $2', employee_id, 'employee')
        if employee:
            await state.update_data(assigned_employee_id=employee_id)
            await callback_query.message.answer(f"Сотрудник '<b>{employee['full_name']}</b>' выбран. Теперь введите название задачи:",
                                                 reply_markup=get_keyboard_with_back_button([]), parse_mode='HTML')
            await state.set_state(ManagerStates.waiting_for_task_title)
            user_logger.info(f"Менеджер {callback_query.from_user.id} выбрал сотрудника {employee_id} для назначения задачи")
        else:
            await callback_query.message.answer("Сотрудник с таким User ID не является сотрудником или не найден. Пожалуйста, выберите корректного сотрудника.",
                                                 reply_markup=get_main_menu_keyboard('manager'))
            await state.clear()
            app_logger.warning(f"Сотрудник {employee_id} не найден при назначении задачи")
    await callback_query.answer()

@router.message(ManagerStates.waiting_for_task_title)
async def process_task_title(message: Message, state: FSMContext):
    task_title = message.text
    await state.update_data(task_title=task_title)
    await message.answer("Теперь введите описание задачи:",
                         reply_markup=get_keyboard_with_back_button([]))
    user_logger.info(f"Менеджер {message.from_user.id} ввел название задачи: {task_title}")
    await state.set_state(ManagerStates.waiting_for_task_description)

@router.message(ManagerStates.waiting_for_task_description)
async def process_task_description(message: Message, state: FSMContext, pool: asyncpg.Pool, bot: Bot):
    task_description = message.text
    data = await state.get_data()
    assigned_employee_id = data.get('assigned_employee_id')
    task_title = data.get('task_title')
    manager_id = message.from_user.id

    if not all([assigned_employee_id, task_title, task_description]):
        await message.answer("Ошибка: Не удалось получить все данные для создания задачи. Попробуйте снова.",
                             reply_markup=get_main_menu_keyboard('manager'))
        await state.clear()
        app_logger.error(f"Ошибка при создании задачи менеджером {manager_id}: недостаток данных")
        return

    async with pool.acquire() as conn:
        manager_org_id = await conn.fetchval('SELECT organization_id FROM users WHERE user_id = $1', manager_id)
        if not manager_org_id:
            await message.answer("Ошибка: Вы не привязаны ни к одной организации. Невозможно создать задачу.",
                                 reply_markup=get_main_menu_keyboard('manager'))
            await state.clear()
            app_logger.error(f"Менеджер {manager_id} не привязан к организации при создании задачи")
            return

        try:
            new_task = await conn.fetchrow('''
                INSERT INTO tasks (title, description, manager_id, employee_id, organization_id, status)
                VALUES ($1, $2, $3, $4, $5, 'new') RETURNING task_id
            ''',
                task_title, task_description, manager_id, assigned_employee_id, manager_org_id
            )
            new_task_id = new_task['task_id']

            await message.answer(f"Задача \'{task_title}\' успешно назначена сотруднику.",
                                 reply_markup=get_main_menu_keyboard('manager'))
            await state.clear()
            user_logger.info(f"Менеджер {manager_id} создал задачу {new_task_id} для сотрудника {assigned_employee_id}")

            notification_text = (
                f"🔔 <b>Новая задача назначена!</b>\n\n"
                f"<b>Название:</b> {task_title}\n"
                f"<b>Описание:</b> {task_description}\n"
                f"<b>Менеджер:</b> {message.from_user.full_name}\n"
                f"<b>Статус:</b> 🆕 Новая"
            )
            inline_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Изменить статус", callback_data=f"change_task_direct_{new_task_id}")]])
            await send_task_notification(bot, assigned_employee_id, notification_text, reply_markup=inline_kb, parse_mode='HTML')
            user_logger.info(f"Отправлено уведомление сотруднику {assigned_employee_id} о новой задаче {new_task_id}")

        except Exception as e:
            await message.answer(f"Произошла ошибка при создании задачи: {e}",
                                 reply_markup=get_main_menu_keyboard('manager'))
            await state.clear()
            app_logger.error(f"Ошибка при создании задачи менеджером {manager_id}: {e}")


async def format_manager_tasks_response(tasks: list, title: str, status_filter: str = None) -> str:
    response = f"<b>{title}:</b>\n\n"
    if tasks:
        for task in tasks:
            manager_name = task['manager_name'] if task['manager_name'] else "Неизвестно"
            employee_name = task['employee_name'] if task['employee_name'] else "Неизвестно"
            status_emoji = status_emojis.get(task['status'], '')
            status_display = status_display_map.get(task['status'], task['status'].capitalize())
            response += (
                f"---------------------------\n"
                f"<b>ID Задачи:</b> {task['task_id']}\n"
                f"<b>Название:</b> {task['title']}\n"
                f"<b>Описание:</b> {task['description']}\n"
                f"<b>Менеджер:</b> {manager_name}\n"
                f"<b>Сотрудник:</b> {employee_name}\n"
                f"<b>Статус:</b> {status_emoji} {status_display}\n"
                f"---------------------------\n"
            )
    else:
        response += "Пока нет задач в этой категории.\n"
    
    if status_filter in ['completed', 'rejected']:
        response += "\n<b>(Отображены только 20 последних задач)</b>"

    return response


@router.message(F.text == "Все задачи")
async def track_all_tasks_prompt(message: Message, pool: asyncpg.Pool):
    if not await is_manager(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        app_logger.warning(f"Пользователь {message.from_user.id} попытался просмотреть задачи без прав менеджера")
        return
    tasks = await get_manager_tasks_by_status(message.from_user.id, pool)
    await message.answer(await format_manager_tasks_response(tasks))
    user_logger.info(f"Менеджер {message.from_user.id} просмотрел все задачи")

@router.message(F.text == "Новые задачи")
async def track_new_tasks_prompt(message: Message, pool: asyncpg.Pool):
    if not await is_manager(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        app_logger.warning(f"Пользователь {message.from_user.id} попытался просмотреть новые задачи без прав менеджера")
        return

    manager_id = message.from_user.id
    async with pool.acquire() as conn:
        tasks = await get_manager_tasks_by_status(manager_id, pool, 'new')
        response_text = await format_manager_tasks_response(tasks, "Новые задачи", 'new')
        await message.answer(response_text, parse_mode='HTML')
        user_logger.info(f"Менеджер {manager_id} просмотрел новые задачи")

@router.message(F.text == "Принятые задачи")
async def track_accepted_tasks_prompt(message: Message, pool: asyncpg.Pool):
    if not await is_manager(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        app_logger.warning(f"Пользователь {message.from_user.id} попытался просмотреть принятые задачи без прав менеджера")
        return

    manager_id = message.from_user.id
    async with pool.acquire() as conn:
        tasks = await get_manager_tasks_by_status(manager_id, pool, 'accepted')
        response_text = await format_manager_tasks_response(tasks, "Принятые задачи", 'accepted')
        await message.answer(response_text, parse_mode='HTML')
        user_logger.info(f"Менеджер {manager_id} просмотрел принятые задачи")

@router.message(F.text == "Выполненные задачи")
async def track_completed_tasks_prompt(message: Message, pool: asyncpg.Pool):
    if not await is_manager(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        app_logger.warning(f"Пользователь {message.from_user.id} попытался просмотреть выполненные задачи без прав менеджера")
        return

    manager_id = message.from_user.id
    async with pool.acquire() as conn:
        tasks = await get_manager_tasks_by_status(manager_id, pool, 'completed')
        response_text = await format_manager_tasks_response(tasks, "Выполненные задачи", 'completed')
        await message.answer(response_text, parse_mode='HTML')
        user_logger.info(f"Менеджер {manager_id} просмотрел выполненные задачи")

@router.message(F.text == "Отказанные задачи")
async def track_rejected_tasks_prompt(message: Message, pool: asyncpg.Pool):
    if not await is_manager(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        app_logger.warning(f"Пользователь {message.from_user.id} попытался просмотреть отказанные задачи без прав менеджера")
        return

    manager_id = message.from_user.id
    async with pool.acquire() as conn:
        tasks = await get_manager_tasks_by_status(manager_id, pool, 'rejected')
        response_text = await format_manager_tasks_response(tasks, "Отказанные задачи", 'rejected')
        await message.answer(response_text, parse_mode='HTML')
        user_logger.info(f"Менеджер {manager_id} просмотрел отказанные задачи")