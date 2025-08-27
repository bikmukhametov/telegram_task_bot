from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
import asyncpg
import asyncio
import logging

from keyboards import get_main_menu_keyboard, get_task_status_keyboard, get_keyboard_with_back_button
from states import EmployeeStates
from handlers.manager_handlers import send_task_notification

router = Router()

app_logger = logging.getLogger('app')
user_logger = logging.getLogger('user_actions')

async def get_tasks_by_status(employee_id: int, pool: asyncpg.Pool, status: str = None):
    async with pool.acquire() as conn:
        if status:
            if status in ['completed', 'rejected']:
                tasks = await conn.fetch('''
                    SELECT t.task_id, t.title, t.description, t.status, u.full_name as manager_name
                    FROM tasks t
                    JOIN users u ON t.manager_id = u.user_id
                    WHERE t.employee_id = $1 AND t.status = $2
                    ORDER BY t.created_at DESC
                    LIMIT 20
                ''', employee_id, status)
            else:
                tasks = await conn.fetch('''
                    SELECT t.task_id, t.title, t.description, t.status, u.full_name as manager_name
                    FROM tasks t
                    JOIN users u ON t.manager_id = u.user_id
                    WHERE t.employee_id = $1 AND t.status = $2
                    ORDER BY t.created_at DESC
                ''', employee_id, status)
        else:
            tasks = await conn.fetch('''
                SELECT t.task_id, t.title, t.description, t.status, u.full_name as manager_name
                FROM tasks t
                JOIN users u ON t.manager_id = u.user_id
                WHERE t.employee_id = $1
                ORDER BY t.created_at DESC
            ''', employee_id)
        return tasks

async def format_tasks_response(tasks, status_filter: str = None):
    if tasks:
        response = "Ваши задачи:\n"
        status_emojis = {
            'new': '🆕',
            'accepted': '✅',
            'completed': '🎉',
            'rejected': '❌'
        }
        for task in tasks:
            status_map = {
                'new': 'Новая',
                'accepted': 'Принята',
                'completed': 'Выполнена',
                'rejected': 'Отказана'
            }
            display_status = status_map.get(task['status'], task['status'])
            emoji = status_emojis.get(task['status'], '')
            response += (f"---------------------------\n"
                         f"ID: {task['task_id']}\n"
                         f"Название: {task['title']}\n"
                         f"Описание: {task['description']}\n"
                         f"Статус: {emoji} {display_status}\n"
                         f"Менеджер: {task['manager_name']}\n")
        
        if status_filter in ['completed', 'rejected']:
            response += "\n<b>(Отображены только 20 последних задач)</b>"
    else:
        response = "У вас пока нет задач."
    return response

async def is_employee(user_id: int, pool: asyncpg.Pool) -> bool:
    async with pool.acquire() as conn:
        user = await conn.fetchrow('SELECT role FROM users WHERE user_id = $1', user_id)
        return user and user['role'] == 'employee'


@router.message(F.text == "Мои новые задачи")
async def view_my_new_tasks(message: Message, pool: asyncpg.Pool):
    if not await is_employee(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        app_logger.warning(f"Пользователь {message.from_user.id} попытался просмотреть новые задачи без прав сотрудника")
        return
    tasks = await get_tasks_by_status(message.from_user.id, pool, 'new')
    await message.answer(await format_tasks_response(tasks))
    user_logger.info(f"Сотрудник {message.from_user.id} просмотрел новые задачи")

@router.message(F.text == "Мои принятые задачи")
async def view_my_accepted_tasks(message: Message, pool: asyncpg.Pool):
    if not await is_employee(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        app_logger.warning(f"Пользователь {message.from_user.id} попытался просмотреть принятые задачи без прав сотрудника")
        return
    tasks = await get_tasks_by_status(message.from_user.id, pool, 'accepted')
    await message.answer(await format_tasks_response(tasks))
    user_logger.info(f"Сотрудник {message.from_user.id} просмотрел принятые задачи")

@router.message(F.text == "Мои выполненные задачи")
async def view_my_completed_tasks(message: Message, pool: asyncpg.Pool):
    if not await is_employee(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        app_logger.warning(f"Пользователь {message.from_user.id} попытался просмотреть выполненные задачи без прав сотрудника")
        return
    tasks = await get_tasks_by_status(message.from_user.id, pool, 'completed')
    await message.answer(await format_tasks_response(tasks, 'completed'))
    user_logger.info(f"Сотрудник {message.from_user.id} просмотрел выполненные задачи")

@router.message(F.text == "Мои отказанные задачи")
async def view_my_rejected_tasks(message: Message, pool: asyncpg.Pool):
    if not await is_employee(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        app_logger.warning(f"Пользователь {message.from_user.id} попытался просмотреть отказанные задачи без прав сотрудника")
        return
    tasks = await get_tasks_by_status(message.from_user.id, pool, 'rejected')
    await message.answer(await format_tasks_response(tasks, 'rejected'))
    user_logger.info(f"Сотрудник {message.from_user.id} просмотрел отказанные задачи")

@router.callback_query(F.data.startswith("change_task_direct_"))
async def direct_change_task_status(callback_query: CallbackQuery, state: FSMContext, pool: asyncpg.Pool, bot: Bot):
    await callback_query.answer()
    await state.clear()

    task_id_from_callback = int(callback_query.data.split('_')[3])
    employee_id = callback_query.from_user.id

    async with pool.acquire() as conn:
        task = await conn.fetchrow('SELECT task_id, title, description, status, manager_id, employee_id FROM tasks WHERE task_id = $1 AND employee_id = $2 AND status IN ($3, $4)',
                                   task_id_from_callback, employee_id, 'new', 'accepted')

        if not task:
            await callback_query.message.edit_text("Этой задачи больше нет или ее статус уже изменен.", reply_markup=None)
            await state.set_state(None)
            app_logger.warning(f"Сотрудник {employee_id} попытался изменить статус несуществующей задачи {task_id_from_callback}")
            return

        await state.update_data(tasks_to_process=[task['task_id']], current_task_index=0,
                                current_task_id=task['task_id'], # Still store for immediate use
                                manager_id_for_notification=task['manager_id'],
                                task_title=task['title'],
                                task_description=task['description'])

        await _process_next_employee_task(callback_query.message.chat.id, state, pool, bot, message_id_to_delete=callback_query.message.message_id)
        user_logger.info(f"Сотрудник {employee_id} начал изменение статуса задачи {task_id_from_callback} через прямое уведомление")

@router.message(F.text == "Изменить статус задач")
async def change_task_status_prompt(message: Message, state: FSMContext, pool: asyncpg.Pool, bot: Bot):
    await state.clear()

    employee_id = message.from_user.id
    async with pool.acquire() as conn:
        tasks = await conn.fetch('SELECT task_id, title, description, status, manager_id, employee_id FROM tasks WHERE employee_id = $1 AND status IN ($2, $3) ORDER BY created_at ASC',
                                 employee_id, 'new', 'accepted')

    if not tasks:
        await message.answer("У вас нет новых или принятых задач для изменения статуса.")
        await state.set_state(None)
        user_logger.info(f"Сотрудник {employee_id} попытался изменить статус задач (нет задач для изменения)")
        return

    await state.update_data(tasks_to_process=[t['task_id'] for t in tasks], current_task_index=0)
    user_logger.info(f"Сотрудник {employee_id} начал изменение статуса {len(tasks)} задач через меню")
    await _process_next_employee_task(message.chat.id, state, pool, bot)

@router.callback_query(F.data == "cancel_task_status_change")
async def cancel_task_status_change(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await state.clear()
    await callback_query.message.edit_text("Изменение статуса задач отменено. Возвращаюсь в главное меню.",
                                           reply_markup=None)
    await callback_query.message.answer("Главное меню:",
                                         reply_markup=get_main_menu_keyboard('employee'))
    user_logger.info(f"Сотрудник {callback_query.from_user.id} отменил изменение статуса задач")
    await callback_query.answer()

@router.callback_query(F.data.startswith("status_"))
async def set_task_status(callback_query: CallbackQuery, state: FSMContext, pool: asyncpg.Pool, bot: Bot):
    await callback_query.answer()
    new_status = callback_query.data.split('_')[1]
    task_id_from_callback = int(callback_query.data.split('_')[2])

    data = await state.get_data()
    tasks_to_process = data.get('tasks_to_process', [])
    current_task_index = data.get('current_task_index', 0)

    current_task_id = task_id_from_callback
    target_message_id = callback_query.message.message_id

    if not current_task_id:
        try:
            await bot.edit_message_text("Произошла ошибка: не удалось определить текущую задачу. Попробуйте снова.",
                                        chat_id=callback_query.message.chat.id, message_id=target_message_id, reply_markup=None)
        except Exception as e:
            pass
        await state.clear()
        app_logger.error(f"Ошибка при изменении статуса задачи: не удалось определить текущую задачу для сотрудника {callback_query.from_user.id}")
        return

    employee_id = callback_query.from_user.id

    async with pool.acquire() as conn:
        current_db_task = await conn.fetchrow('SELECT status, title, description, manager_id FROM tasks WHERE task_id = $1', current_task_id)

        if not current_db_task:
            try:
                await bot.edit_message_text("Ошибка: Задача не найдена в базе данных.",
                                            chat_id=callback_query.message.chat.id, message_id=target_message_id, reply_markup=None)
            except Exception as e:
                pass
            await state.clear()
            app_logger.error(f"Ошибка при изменении статуса задачи: задача {current_task_id} не найдена для сотрудника {employee_id}")
            return

        old_status = current_db_task['status']
        task_title = current_db_task['title']
        manager_id_for_notification = current_db_task['manager_id']

        status_mapping = {
            'new': 'Новая',
            'accepted': 'Принята',
            'completed': 'Выполнена',
            'rejected': 'Отказана'
        }
        old_status_display = status_mapping.get(old_status, old_status)
        new_status_display = status_mapping.get(new_status, new_status)

        status_emojis = {
            'new': '🆕',
            'accepted': '✅',
            'completed': '🎉',
            'rejected': '❌'
        }
        old_emoji = status_emojis.get(old_status, '')
        new_emoji = status_emojis.get(new_status, '')

        edit_text_message = ""
        if old_status in ['completed', 'rejected']:
            edit_text_message = f"Статус задачи <b>{task_title}</b> (ID: {current_task_id}) уже {old_emoji} <b>{old_status_display}</b>. Изменение невозможно."
            user_logger.info(f"Сотрудник {employee_id} попытался изменить статус задачи {current_task_id} с {old_status} на {new_status}, но задача уже в конечном статусе")
        elif old_status == new_status:
            edit_text_message = f"Статус задачи <b>{task_title}</b> (ID: {current_task_id}) уже {old_emoji} <b>{old_status_display}</b>."
            user_logger.info(f"Сотрудник {employee_id} попытался изменить статус задачи {current_task_id} на тот же: {new_status}")
        else:
            await conn.execute('UPDATE tasks SET status = $1 WHERE task_id = $2', new_status, current_task_id)
            edit_text_message = f"Статус задачи <b>{task_title}</b> (ID: {current_task_id}) изменен на {new_emoji} <b>{new_status_display}</b>."
            user_logger.info(f"Сотрудник {employee_id} изменил статус задачи {current_task_id} с {old_status} на {new_status}")

            if manager_id_for_notification:
                employee_name = callback_query.from_user.full_name
                notification_text = (
                    f"<b>Уведомление:</b> Сотрудник <b>{employee_name}</b> (ID: {employee_id}) "
                    f"изменил статус задачи <b>{task_title}</b> (ID: {current_task_id})\n"
                    f"с {old_emoji} <b>{old_status_display}</b> на {new_emoji} <b>{new_status_display}</b>."
                )
                await send_task_notification(bot, manager_id_for_notification, notification_text, parse_mode='HTML')
                user_logger.info(f"Отправлено уведомление менеджеру {manager_id_for_notification} об изменении статуса задачи {current_task_id}")
    try:
        await bot.edit_message_text(edit_text_message,
                                    chat_id=callback_query.message.chat.id, message_id=target_message_id, reply_markup=None, parse_mode='HTML')
    except Exception as e:
        app_logger.error(f"Ошибка при редактировании сообщения для сотрудника {employee_id}: {e}")

    if tasks_to_process and current_task_id == tasks_to_process[current_task_index] and len(tasks_to_process) > current_task_index + 1:
        await state.update_data(current_task_index=current_task_index + 1)
        await _process_next_employee_task(callback_query.message.chat.id, state, pool, bot, current_task_index + 1)
    else:
        await state.clear()

async def _process_next_employee_task(chat_id: int, state: FSMContext, pool: asyncpg.Pool, bot: Bot, start_index: int = 0, message_id_to_delete: int = None):
    data = await state.get_data()
    tasks_to_process = data.get('tasks_to_process', [])

    next_task = None
    
    for i in range(start_index, len(tasks_to_process)):
        task_id = tasks_to_process[i]
        await asyncio.sleep(0.1) 

        async with pool.acquire() as conn:
            db_task = await conn.fetchrow('''
                SELECT t.task_id, t.title, t.description, t.status, t.manager_id, t.employee_id, u.full_name as manager_name
                FROM tasks t
                JOIN users u ON t.manager_id = u.user_id
                WHERE t.task_id = $1
            ''',
                                          task_id)
            
            if db_task and db_task['employee_id'] == chat_id and db_task['status'] in ['new', 'accepted']:
                next_task = db_task
                await state.update_data(current_task_index=i,
                                        current_task_id=next_task['task_id'],
                                        manager_id_for_notification=next_task['manager_id'],
                                        task_title=next_task['title'],
                                        task_description=next_task['description'],
                                        manager_name=next_task['manager_name'])
                break
            else:
                pass
    
    if next_task:
        status_mapping = {
            'new': 'Новая',
            'accepted': 'Принята',
            'completed': 'Выполнена',
            'rejected': 'Отказана'
        }
        status_emojis = {
            'new': '🆕',
            'accepted': '✅',
            'completed': '🎉',
            'rejected': '❌'
        }
        current_status_emoji = status_emojis.get(next_task['status'], '')
        task_info_message = (
            f"<b>Название:</b> {next_task['title']}\n"
            f"<b>Описание:</b> {next_task['description']}\n"
            f"<b>Менеджер:</b> <b>{next_task['manager_name']}</b>\n"
            f"<b>Статус:</b> {current_status_emoji} {status_mapping.get(next_task['status'], next_task['status'])}"
        )
        await state.set_state(EmployeeStates.waiting_for_task_to_change_status)
        
        if len(tasks_to_process) == 1 and start_index == 0:
            sent_message = await bot.send_message(chat_id, task_info_message, reply_markup=get_task_status_keyboard(next_task['task_id'], include_back=False), parse_mode='HTML')
            await state.update_data(last_sent_task_message_id=sent_message.message_id)

            if message_id_to_delete:
                try:
                    await bot.delete_message(chat_id, message_id_to_delete)
                except Exception as e:
                    app_logger.error(f"Ошибка при удалении сообщения для сотрудника {chat_id}: {e}")
        else:
            sent_message = await bot.send_message(chat_id, task_info_message, reply_markup=get_task_status_keyboard(next_task['task_id'], include_back=True), parse_mode='HTML')
            await state.update_data(last_sent_task_message_id=sent_message.message_id)
    else:
        await state.clear()
        if len(tasks_to_process) > 1:
            await bot.send_message(chat_id, "✅ Все новые и принятые задачи обработаны.",
                                         reply_markup=get_main_menu_keyboard('employee'))
            user_logger.info(f"Сотрудник {chat_id} завершил изменение статуса всех задач")

@router.message(EmployeeStates.waiting_for_task_to_change_status)
async def process_task_for_status_change(message: Message, state: FSMContext, pool: asyncpg.Pool, bot: Bot):
    await message.answer("Пожалуйста, используйте кнопки для изменения статуса.",
                         reply_markup=get_main_menu_keyboard('employee'))
    await state.clear()
    user_logger.info(f"Сотрудник {message.from_user.id} попытался использовать текст вместо кнопок для изменения статуса")