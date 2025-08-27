from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
import asyncpg
import logging

from keyboards import (get_main_menu_keyboard, get_confirm_delete_org_keyboard, 
                     get_confirm_assign_manager_keyboard, get_keyboard_with_back_button, 
                     get_users_for_assign_manager_keyboard, get_managers_for_remove_keyboard, 
                     get_organizations_for_assign_manager_keyboard, get_confirm_reset_keyboard)
from states import AdminStates
from config import ADMIN_ID
from instructions import MANAGER_INSTRUCTIONS

router = Router()

app_logger = logging.getLogger('app')
user_logger = logging.getLogger('user_actions')

async def is_admin(user_id: int, pool: asyncpg.Pool) -> bool:
    async with pool.acquire() as conn:
        user = await conn.fetchrow('SELECT role FROM users WHERE user_id = $1', user_id)
        return user and user['role'] == 'admin'

@router.message(F.text == "Просмотр организаций")
async def view_organizations(message: Message, pool: asyncpg.Pool):
    if not await is_admin(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        app_logger.warning(f"Пользователь {message.from_user.id} попытался просмотреть организации без прав администратора")
        return

    async with pool.acquire() as conn:
        organizations = await conn.fetch('SELECT * FROM organizations')
        if organizations:
            response = "Список организаций:\n"
            for org in organizations:
                response += f"- ID: {org['org_id']}, Название: {org['name']}\n"
            await message.answer(response)
            user_logger.info(f"Администратор {message.from_user.id} просмотрел список организаций")
        else:
            await message.answer("Организаций пока нет.")
            user_logger.info(f"Администратор {message.from_user.id} просмотрел список организаций (пусто)")

@router.message(F.text == "Создать организацию")
async def create_organization_prompt(message: Message, state: FSMContext, pool: asyncpg.Pool):
    if not await is_admin(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        app_logger.warning(f"Пользователь {message.from_user.id} попытался создать организацию без прав администратора")
        return
    await message.answer("Введите название новой организации:",
                         reply_markup=get_keyboard_with_back_button([]))
    await state.set_state(AdminStates.waiting_for_org_name_to_create)
    user_logger.info(f"Администратор {message.from_user.id} начал создание организации")

@router.message(AdminStates.waiting_for_org_name_to_create)
async def process_create_organization(message: Message, state: FSMContext, pool: asyncpg.Pool):
    org_name = message.text
    admin_id = message.from_user.id
    async with pool.acquire() as conn:
        try:
            await conn.execute('INSERT INTO organizations (name) VALUES ($1)', org_name)
            await message.answer(f"Организация '{org_name}' успешно создана.",
                                 reply_markup=get_main_menu_keyboard('admin'))
            user_logger.info(f"Администратор {admin_id} создал организацию: {org_name}")
            await state.clear()
        except asyncpg.exceptions.UniqueViolationError:
            await message.answer("Организация с таким названием уже существует. Пожалуйста, введите другое название:")
            app_logger.warning(f"Попытка создать организацию с существующим именем: {org_name}")
        except Exception as e:
            await message.answer(f"Произошла ошибка при создании организации: {e}")
            app_logger.error(f"Ошибка при создании организации: {e}")
            await state.clear()


@router.message(F.text == "Удалить организацию")
async def delete_organization_prompt(message: Message, state: FSMContext, pool: asyncpg.Pool):
    if not await is_admin(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        app_logger.warning(f"Пользователь {message.from_user.id} попытался удалить организацию без прав администратора")
        return

    async with pool.acquire() as conn:
        organizations = await conn.fetch('SELECT org_id, name FROM organizations')
        if organizations:
            response = "Выберите организацию для удаления (введите ID):\n"
            for org in organizations:
                response += f"- ID: {org['org_id']}, Название: {org['name']}\n"
            await message.answer(response, reply_markup=get_keyboard_with_back_button([]))
            await state.set_state(AdminStates.waiting_for_org_name_to_delete)
            user_logger.info(f"Администратор {message.from_user.id} начал удаление организации")
        else:
            await message.answer("Организаций для удаления нет.", reply_markup=get_main_menu_keyboard('admin'))
            user_logger.info(f"Администратор {message.from_user.id} попытался удалить организацию (нет организаций)")

@router.message(AdminStates.waiting_for_org_name_to_delete)
async def process_delete_organization(message: Message, state: FSMContext, pool: asyncpg.Pool):
    org_id_str = message.text
    try:
        org_id = int(org_id_str)
    except ValueError:
        await message.answer("Неверный ID организации. Пожалуйста, введите числовой ID.")
        app_logger.warning(f"Неверный ID организации при удалении: {org_id_str}")
        return

    async with pool.acquire() as conn:
        org = await conn.fetchrow('SELECT name FROM organizations WHERE org_id = $1', org_id)
        if org:
            await message.answer(f"Вы уверены, что хотите удалить организацию '{org['name']}'?",
                                 reply_markup=get_confirm_delete_org_keyboard(org_id))
            await state.clear()
            user_logger.info(f"Администратор {message.from_user.id} подтверждает удаление организации {org_id} ({org['name']})")
        else:
            await message.answer("Организация с таким ID не найдена. Пожалуйста, введите корректный ID.",
                                 reply_markup=get_keyboard_with_back_button([]))
            app_logger.warning(f"Организация с ID {org_id} не найдена при удалении")


@router.callback_query(F.data.startswith("confirm_delete_org_"))
async def confirm_delete_organization(callback_query: CallbackQuery, pool: asyncpg.Pool):
    org_id = int(callback_query.data.split('_')[3])
    admin_id = callback_query.from_user.id
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('''
                UPDATE users
                SET role = 'user', organization_id = NULL
                WHERE organization_id = $1 AND role IN ('employee', 'manager')
            ''', org_id)

            org_name = await conn.fetchval('SELECT name FROM organizations WHERE org_id = $1', org_id)
            await conn.execute('DELETE FROM organizations WHERE org_id = $1', org_id)

        await callback_query.message.edit_text(f"Организация с ID {org_id} успешно удалена. Роли сотрудников и менеджеров сброшены.",
                                             reply_markup=None)
        await callback_query.message.answer("Главное меню:", reply_markup=get_main_menu_keyboard('admin'))
        user_logger.info(f"Администратор {admin_id} удалил организацию {org_id} ({org_name})")
    await callback_query.answer()

@router.callback_query(F.data == "cancel_delete_org")
async def cancel_delete_organization(callback_query: CallbackQuery):
    await callback_query.message.edit_text("Удаление организации отменено.", reply_markup=None)
    await callback_query.message.answer("Главное меню:", reply_markup=get_main_menu_keyboard('admin'))
    user_logger.info(f"Администратор {callback_query.from_user.id} отменил удаление организации")
    await callback_query.answer()


@router.message(F.text == "Назначить менеджера")
async def assign_manager_prompt(message: Message, state: FSMContext, pool: asyncpg.Pool):
    if not await is_admin(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        app_logger.warning(f"Пользователь {message.from_user.id} попытался назначить менеджера без прав администратора")
        return

    async with pool.acquire() as conn:
        users = await conn.fetch('SELECT user_id, full_name, role FROM users WHERE role = $1', 'user')
        if users:
            await message.answer("Выберите пользователя, которого хотите назначить менеджером:",
                                 reply_markup=get_users_for_assign_manager_keyboard(users))
            await state.set_state(AdminStates.waiting_for_manager_id)
            user_logger.info(f"Администратор {message.from_user.id} начал назначение менеджера")
        else:
            await message.answer("Нет доступных пользователей для назначения менеджером.",
                                 reply_markup=get_main_menu_keyboard('admin'))
            user_logger.info(f"Администратор {message.from_user.id} попытался назначить менеджера (нет пользователей)")

@router.callback_query(F.data.startswith("select_user_assign_manager_"))
async def select_user_to_assign_manager(callback_query: CallbackQuery, state: FSMContext, pool: asyncpg.Pool):
    user_id = int(callback_query.data.split('_')[4])
    await callback_query.message.edit_reply_markup(reply_markup=None)

    async with pool.acquire() as conn:
        user = await conn.fetchrow('SELECT full_name, role FROM users WHERE user_id = $1', user_id)
        if user:
            await state.update_data(manager_user_id=user_id)
            organizations = await conn.fetch('SELECT org_id, name FROM organizations')
            if organizations:
                response = f"Пользователь '<b>{user['full_name']}</b>' (Текущая роль: {user['role']}) выбран. " \
                           f"Теперь выберите организацию, в которую назначить его менеджером:"
                await callback_query.message.answer(response, reply_markup=get_organizations_for_assign_manager_keyboard(organizations), parse_mode='HTML')
                user_logger.info(f"Администратор {callback_query.from_user.id} выбрал пользователя {user_id} для назначения менеджером")
            else:
                await callback_query.message.answer("Нет доступных организаций для назначения менеджера.",
                                                     reply_markup=get_main_menu_keyboard('admin'))
                await state.clear()
                user_logger.info(f"Администратор {callback_query.from_user.id} не смог назначить менеджера (нет организаций)")
        else:
            await callback_query.message.answer("Пользователь с таким User ID не найден. Пожалуйста, выберите корректного пользователя.",
                                                 reply_markup=get_main_menu_keyboard('admin'))
            await state.clear()
            app_logger.warning(f"Пользователь {user_id} не найден при назначении менеджера")
    await callback_query.answer()

@router.callback_query(F.data.startswith("select_org_assign_manager_"))
async def process_assign_manager_by_button(callback_query: CallbackQuery, state: FSMContext, pool: asyncpg.Pool, bot: Bot):
    await callback_query.answer()
    org_id = int(callback_query.data.split('_')[4])
    admin_id = callback_query.from_user.id

    data = await state.get_data()
    manager_user_id = data.get('manager_user_id')

    if not manager_user_id:
        await callback_query.message.edit_text("Ошибка: Не удалось найти пользователя для назначения. Попробуйте начать сначала.", reply_markup=None)
        await callback_query.message.answer("Главное меню:", reply_markup=get_main_menu_keyboard('admin'))
        await state.clear()
        app_logger.error(f"Ошибка при назначении менеджера: не найден manager_user_id для администратора {admin_id}")
        return

    async with pool.acquire() as conn:
        org = await conn.fetchrow('SELECT name FROM organizations WHERE org_id = $1', org_id)
        if org:
            await conn.execute('UPDATE users SET role = $1, organization_id = $2 WHERE user_id = $3',
                               'manager', org_id, manager_user_id)
            await callback_query.message.edit_text(f"Пользователь с ID {manager_user_id} назначен менеджером "
                                                 f"в организации '<b>{org['name']}</b>'.",
                                                 reply_markup=None, parse_mode='HTML')
            await callback_query.message.answer("Главное меню:", reply_markup=get_main_menu_keyboard('admin'))
            await state.clear()
            user_logger.info(f"Администратор {admin_id} назначил пользователя {manager_user_id} менеджером организации {org_id} ({org['name']})")

            try:
                await bot.send_message(manager_user_id, MANAGER_INSTRUCTIONS, parse_mode='HTML')
                await bot.send_message(manager_user_id, "Ваше главное меню:", reply_markup=get_main_menu_keyboard('manager'))
                user_logger.info(f"Отправлены инструкции новому менеджеру {manager_user_id}")
            except Exception as e:
                app_logger.error(f"Не удалось отправить сообщение менеджеру {manager_user_id}: {e}")
        else:
            await callback_query.message.edit_text("Организация с таким ID не найдена. Пожалуйста, выберите корректную организацию.",
                                                 reply_markup=None)
            await callback_query.message.answer("Главное меню:", reply_markup=get_main_menu_keyboard('admin'))
            await state.clear()
            app_logger.warning(f"Организация {org_id} не найдена при назначении менеджера")

@router.message(F.text == "Статистика")
async def view_statistics(message: Message, pool: asyncpg.Pool):
    if not await is_admin(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        app_logger.warning(f"Пользователь {message.from_user.id} попытался посмотреть статистику без прав администратора")
        return

    async with pool.acquire() as conn:
        total_users = await conn.fetchval('SELECT COUNT(*) FROM users')
        total_organizations = await conn.fetchval('SELECT COUNT(*) FROM organizations')
        total_tasks = await conn.fetchval('SELECT COUNT(*) FROM tasks')
        
        total_managers = await conn.fetchval('SELECT COUNT(*) FROM users WHERE role = $1', 'manager')
        total_employees = await conn.fetchval('SELECT COUNT(*) FROM users WHERE role = $1', 'employee')

        tasks_by_status = await conn.fetch('SELECT status, COUNT(*) FROM tasks GROUP BY status')

        tasks_per_organization = await conn.fetch('''
            SELECT o.name, COUNT(t.task_id) as task_count
            FROM organizations o
            LEFT JOIN tasks t ON o.org_id = t.organization_id
            GROUP BY o.name
            ORDER BY o.name
        ''')

        tasks_by_manager = await conn.fetch('''
            SELECT u.full_name, COUNT(t.task_id) as assigned_tasks_count
            FROM users u
            LEFT JOIN tasks t ON u.user_id = t.manager_id
            WHERE u.role = 'manager'
            GROUP BY u.full_name
            ORDER BY u.full_name
        ''')

        tasks_completed_by_employee = await conn.fetch('''
            SELECT u.full_name, COUNT(t.task_id) as completed_tasks_count
            FROM users u
            LEFT JOIN tasks t ON u.user_id = t.employee_id
            WHERE u.role = 'employee' AND t.status = 'completed'
            GROUP BY u.full_name
            ORDER BY u.full_name
        ''')

        status_emojis = {
            'new': '🆕',
            'accepted': '✅',
            'completed': '🎉',
            'rejected': '❌'
        }

        status_display_map = {
            'new': 'Новых',
            'accepted': 'Принятых',
            'completed': 'Выполненных',
            'rejected': 'Отказанных'
        }

        stats_text = (
            f"<b>📊 Общая статистика:</b>\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"🏢 Всего организаций: {total_organizations}\n"
            f"📝 Всего задач: {total_tasks}\n"
            f"\n<b>Статистика задач по статусам:</b>\n"
        )

        for status_record in tasks_by_status:
            status_key = status_record['status']
            count = status_record['count']
            display_status = status_display_map.get(status_key, status_key.capitalize())
            emoji = status_emojis.get(status_key, '')
            stats_text += f"{emoji} {display_status}: {count}\n"

        stats_text += f"\n<b>Роли пользователей:</b>\n"
        stats_text += f"🧑‍💻 Всего менеджеров: {total_managers}\n"
        stats_text += f"👨‍🏭 Всего сотрудников: {total_employees}\n"

        if tasks_per_organization:
            stats_text += f"\n<b>Задачи по организациям:</b>\n"
            for org_record in tasks_per_organization:
                stats_text += f"🏢 {org_record['name']}: {org_record['task_count']} задач\n"
        else:
            stats_text += "\nНет задач по организациям.\n"

        if tasks_by_manager:
            stats_text += f"\n<b>Задачи, назначенные менеджерами:</b>\n"
            for manager_record in tasks_by_manager:
                stats_text += f"👤 {manager_record['full_name']}: {manager_record['assigned_tasks_count']} задач\n"
        else:
            stats_text += "\nНет назначенных задач менеджерами.\n"

        if tasks_completed_by_employee:
            stats_text += f"\n<b>Задачи, выполненные сотрудниками:</b>\n"
            for employee_record in tasks_completed_by_employee:
                stats_text += f"✅ {employee_record['full_name']}: {employee_record['completed_tasks_count']} задач\n"
        else:
            stats_text += "\nНет выполненных задач сотрудниками.\n"

        await message.answer(stats_text, parse_mode='HTML')
        user_logger.info(f"Администратор {message.from_user.id} просмотрел статистику")

@router.message(F.text == "Просмотр пользователей")
async def view_all_users(message: Message, pool: asyncpg.Pool):
    if not await is_admin(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        app_logger.warning(f"Пользователь {message.from_user.id} попытался просмотреть пользователей без прав администратора")
        return

    admin_user_id = message.from_user.id
    async with pool.acquire() as conn:
        users = await conn.fetch('''
            SELECT u.user_id, u.full_name, u.role, o.name as organization_name
            FROM users u
            LEFT JOIN organizations o ON u.organization_id = o.org_id
            WHERE u.user_id != $1
            ORDER BY u.full_name
        ''', admin_user_id)

        if users:
            response = "Список пользователей (кроме вас):\n"
            for user in users:
                org_name = user['organization_name'] if user['organization_name'] else "Нет организации"
                response += (f"---------------------------\n"
                             f"<b>ID:</b> {user['user_id']}\n"
                             f"<b>ФИО:</b> {user['full_name']}\n"
                             f"<b>Роль:</b> {user['role']}\n"
                             f"<b>Организация:</b> {org_name}\n"
                             f"---------------------------\n")
            await message.answer(response)
            user_logger.info(f"Администратор {admin_user_id} просмотрел список пользователей")
        else:
            await message.answer("Нет других пользователей для отображения.")
            user_logger.info(f"Администратор {admin_user_id} просмотрел список пользователей (пусто)")

@router.message(F.text == "Удалить менеджера")
async def remove_manager_prompt(message: Message, state: FSMContext, pool: asyncpg.Pool):
    if not await is_admin(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        app_logger.warning(f"Пользователь {message.from_user.id} попытался удалить менеджера без прав администратора")
        return

    async with pool.acquire() as conn:
        managers = await conn.fetch('SELECT user_id, full_name, organization_id FROM users WHERE role = $1', 'manager')
        if managers:
            await message.answer("Выберите менеджера, которого хотите удалить:",
                                 reply_markup=get_managers_for_remove_keyboard(managers))
            await state.set_state(AdminStates.waiting_for_manager_id_to_remove)
            user_logger.info(f"Администратор {message.from_user.id} начал удаление менеджера")
        else:
            await message.answer("Нет менеджеров для удаления.", reply_markup=get_main_menu_keyboard('admin'))
            user_logger.info(f"Администратор {message.from_user.id} попытался удалить менеджера (нет менеджеров)")

@router.callback_query(F.data.startswith("select_manager_remove_"))
async def select_manager_to_remove(callback_query: CallbackQuery, state: FSMContext, pool: asyncpg.Pool, bot: Bot):
    user_id = int(callback_query.data.split('_')[3])
    await callback_query.message.edit_reply_markup(reply_markup=None)

    async with pool.acquire() as conn:
        manager = await conn.fetchrow('SELECT full_name FROM users WHERE user_id = $1 AND role = $2', user_id, 'manager')
        if manager:
            await conn.execute('UPDATE users SET role = $1, organization_id = NULL WHERE user_id = $2', 'user', user_id)
            await callback_query.message.answer(f"Пользователь '<b>{manager['full_name']}</b>' (ID: {user_id}) успешно удален из роли менеджера и стал обычным пользователем.",
                                                 reply_markup=get_main_menu_keyboard('admin'), parse_mode='HTML')
            await state.clear()
            user_logger.info(f"Администратор {callback_query.from_user.id} удалил менеджера {user_id} ({manager['full_name']})")
            
            try:
                await bot.send_message(user_id, f"<b>Уведомление:</b> Ваша роль была изменена на <b>Пользователь</b>. Вы больше не являетесь менеджером.", parse_mode='HTML')
                await bot.send_message(user_id, "Ваше главное меню:", reply_markup=get_main_menu_keyboard('user'))
                user_logger.info(f"Отправлено уведомление пользователю {user_id} об изменении роли")
            except Exception as e:
                app_logger.error(f"Не удалось отправить уведомление пользователю {user_id}: {e}")
        else:
            await callback_query.message.answer("Пользователь с таким User ID не является менеджером или не найден. Пожалуйста, выберите корректного менеджера.",
                                                 reply_markup=get_main_menu_keyboard('admin'))
            await state.clear()
            app_logger.warning(f"Пользователь {user_id} не найден или не является менеджером при удалении")
    await callback_query.answer()

@router.message(F.text == "Сбросить все данные")
async def reset_all_users_prompt(message: Message, state: FSMContext, pool: asyncpg.Pool):
    if not await is_admin(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        return
    
    await message.answer(
        "Вы уверены, что хотите сбросить всех пользователей? "
        "Это действие удалит все данные о пользователях (кроме администраторов), "
        "их роли, задачи и сообщения. Пользователям нужно будет заново пройти регистрацию.",
        reply_markup=get_confirm_reset_keyboard()
    )
    await state.set_state(AdminStates.waiting_for_reset_confirmation)

@router.callback_query(F.data == "confirm_reset", AdminStates.waiting_for_reset_confirmation)
async def confirm_reset_all_users(callback_query: CallbackQuery, state: FSMContext, pool: asyncpg.Pool, bot: Bot):
    admin_id = callback_query.from_user.id
    
    async with pool.acquire() as conn:
        async with conn.transaction():
            users_to_reset = await conn.fetch("SELECT user_id FROM users WHERE role != 'admin'")
            
            for user in users_to_reset:
                user_id = user['user_id']
                try:
                    await bot.send_message(user_id, "Ваш аккаунт был сброшен администратором. "
                                                    "Для продолжения использования бота, пожалуйста, "
                                                    "нажмите на кнопку /start. 👈")
                except Exception as e:
                    app_logger.warning(f"Не удалось отправить сообщение о сбросе пользователю {user_id}: {e}")

            await conn.execute("DELETE FROM tasks")
            await conn.execute("DELETE FROM users WHERE role != 'admin'")
            await conn.execute("DELETE FROM organizations")

    await callback_query.message.edit_text("Все пользователи были сброшены.", reply_markup=None)
    await callback_query.message.answer("Главное меню:", reply_markup=get_main_menu_keyboard('admin'))
    user_logger.info(f"Администратор {admin_id} сбросил всех пользователей.")
    await state.clear()
    await callback_query.answer()

@router.callback_query(F.data == "cancel_reset", AdminStates.waiting_for_reset_confirmation)
async def cancel_reset_all_users(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.message.edit_text("Сброс пользователей отменен.", reply_markup=None)
    await callback_query.message.answer("Главное меню:", reply_markup=get_main_menu_keyboard('admin'))
    await state.clear()
    await callback_query.answer()

@router.message(F.text == "Отправить всем сообщение")
async def broadcast_message_prompt(message: Message, state: FSMContext, pool: asyncpg.Pool):
    if not await is_admin(message.from_user.id, pool):
        await message.answer("У вас нет прав для выполнения этой команды.")
        return
    
    await message.answer("Введите сообщение, которое хотите отправить всем пользователям:",
                         reply_markup=get_keyboard_with_back_button([]))
    await state.set_state(AdminStates.waiting_for_broadcast_message)

@router.message(AdminStates.waiting_for_broadcast_message)
async def process_broadcast_message(message: Message, state: FSMContext, pool: asyncpg.Pool, bot: Bot):
    broadcast_text = message.text
    admin_id = message.from_user.id

    async with pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id FROM users WHERE user_id != $1", admin_id)
    
    sent_count = 0
    failed_count = 0
    
    for user in users:
        try:
            await bot.send_message(user['user_id'], broadcast_text)
            sent_count += 1
        except Exception as e:
            failed_count += 1
            app_logger.error(f"Не удалось отправить сообщение пользователю {user['user_id']}: {e}")

    await message.answer(
        f"Рассылка завершена.\n"
        f"Успешно отправлено: {sent_count}\n"
        f"Не удалось отправить: {failed_count}",
        reply_markup=get_main_menu_keyboard('admin')
    )
    user_logger.info(f"Администратор {admin_id} отправил сообщение '{broadcast_text}' {sent_count} пользователям.")
    await state.clear()