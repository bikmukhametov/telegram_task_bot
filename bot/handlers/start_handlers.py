from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
import asyncpg
import logging

from keyboards import get_start_keyboard, get_main_menu_keyboard, get_keyboard_with_back_button
from states import RegistrationStates
from config import ADMIN_ID

router = Router()

app_logger = logging.getLogger('app')
user_logger = logging.getLogger('user_actions')

# Universal back button handler
@router.message(F.text == "Назад")
async def cmd_back(message: Message, state: FSMContext, pool: asyncpg.Pool):
    current_state = await state.get_state()
    if current_state: # Only clear if there's an active state
        await state.clear()
    user_id = message.from_user.id
    async with pool.acquire() as conn:
        user = await conn.fetchrow('SELECT role FROM users WHERE user_id = $1', user_id)
        user_role = user['role'] if user else 'user'
        await message.answer("Действие отменено. Вы вернулись в главное меню.",
                             reply_markup=get_main_menu_keyboard(user_role))
        user_logger.info(f"Пользователь {user_id} нажал 'Назад', текущая роль: {user_role}")

@router.callback_query(F.data == "cancel_action")
async def cmd_cancel_action(callback_query: CallbackQuery, state: FSMContext, pool: asyncpg.Pool):
    current_state = await state.get_state()
    if current_state: # Only clear if there's an active state
        await state.clear()
    user_id = callback_query.from_user.id
    async with pool.acquire() as conn:
        user = await conn.fetchrow('SELECT role FROM users WHERE user_id = $1', user_id)
        user_role = user['role'] if user else 'user'
        await callback_query.message.edit_text("Действие отменено. Вы вернулись в главное меню.",
                                               reply_markup=None) # Remove inline keyboard
        await callback_query.message.answer("Главное меню:", reply_markup=get_main_menu_keyboard(user_role))
        user_logger.info(f"Пользователь {user_id} отменил действие через callback, текущая роль: {user_role}")
    await callback_query.answer()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, pool: asyncpg.Pool):
    user_id = message.from_user.id
    async with pool.acquire() as conn:
        user = await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)
        if user:
            await message.answer(f"С возвращением, {user['full_name']}! Ваша роль: {user['role']}.",
                                 reply_markup=get_main_menu_keyboard(user['role']))
            user_logger.info(f"Пользователь {user_id} ({user['full_name']}) запустил бота, роль: {user['role']}")
        else:
            await message.answer("Привет! Я бот для управления задачами. Чтобы начать, пожалуйста, зарегистрируйтесь.",
                                 reply_markup=get_start_keyboard())
            user_logger.info(f"Новый пользователь {user_id} запустил бота")

@router.message(F.text == "Зарегистрироваться")
async def register_user_prompt(message: Message, state: FSMContext):
    await message.answer("Пожалуйста, введите ваше полное ФИО:",
                         reply_markup=get_keyboard_with_back_button([])) # Add back button
    await state.set_state(RegistrationStates.waiting_for_full_name)
    user_logger.info(f"Пользователь {message.from_user.id} начал регистрацию")

@router.message(RegistrationStates.waiting_for_full_name)
async def process_full_name(message: Message, state: FSMContext, pool: asyncpg.Pool):
    full_name = message.text
    user_id = message.from_user.id

    async with pool.acquire() as conn:
        try:
            # Check if it's the admin registering
            if user_id == ADMIN_ID:
                await conn.execute('INSERT INTO users (user_id, full_name, role) VALUES ($1, $2, $3)',
                                   user_id, full_name, 'admin')
                await message.answer(f"Вы зарегистрированы как администратор, {full_name}!",
                                     reply_markup=get_main_menu_keyboard('admin'))
                user_logger.info(f"Администратор зарегистрирован: user_id={user_id}, full_name={full_name}")
            else:
                await conn.execute('INSERT INTO users (user_id, full_name) VALUES ($1, $2)', user_id, full_name)
                await message.answer(f"Спасибо, {full_name}! Вы успешно зарегистрированы. Ожидайте назначения роли.",
                                     reply_markup=get_main_menu_keyboard('user'))
                user_logger.info(f"Пользователь зарегистрирован: user_id={user_id}, full_name={full_name}")
            await state.clear()
        except asyncpg.exceptions.UniqueViolationError:
            await message.answer("Вы уже зарегистрированы!")
            await state.clear()
            user = await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)
            if user:
                await message.answer(f"Ваша текущая роль: {user['role']}.",
                                     reply_markup=get_main_menu_keyboard(user['role']))
            app_logger.warning(f"Попытка повторной регистрации: user_id={user_id}")