from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def get_start_keyboard():
    keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Зарегистрироваться")]], resize_keyboard=True, one_time_keyboard=True)
    return keyboard

def get_main_menu_keyboard(role: str):
    if role == 'admin':
        keyboard_layout = [
            [KeyboardButton(text="Создать организацию"), KeyboardButton(text="Удалить организацию")],
            [KeyboardButton(text="Назначить менеджера"), KeyboardButton(text="Удалить менеджера")],
            [KeyboardButton(text="Просмотр организаций"), KeyboardButton(text="Просмотр пользователей")],
            [KeyboardButton(text="Статистика")]
        ]
    elif role == 'manager':
        keyboard_layout = [
            [KeyboardButton(text="Назначить сотрудника"), KeyboardButton(text="Удалить сотрудника"), KeyboardButton(text="Просмотр сотрудников")],
            [KeyboardButton(text="Назначить задачу")],
            [KeyboardButton(text="Новые задачи"), KeyboardButton(text="Принятые задачи")],
            [KeyboardButton(text="Выполненные задачи"), KeyboardButton(text="Отказанные задачи")]
        ]
    elif role == 'employee':
        keyboard_layout = [
            [KeyboardButton(text="Изменить статус задач")],
            [KeyboardButton(text="Мои новые задачи"), KeyboardButton(text="Мои принятые задачи")],
            [KeyboardButton(text="Мои выполненные задачи"), KeyboardButton(text="Мои отказанные задачи")]
        ]
    else:
        keyboard_layout = [] 

    keyboard = ReplyKeyboardMarkup(keyboard=keyboard_layout, resize_keyboard=True)
    return keyboard

def get_task_status_keyboard(task_id: int, include_back: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Принята", callback_data=f"status_accepted_{task_id}")],
        [InlineKeyboardButton(text="Выполнена", callback_data=f"status_completed_{task_id}")],
        [InlineKeyboardButton(text="Отказана", callback_data=f"status_rejected_{task_id}")]
    ]
    if include_back:
        buttons.append([InlineKeyboardButton(text="Назад", callback_data="cancel_task_status_change")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# New function for keyboards with a "Назад" button
def get_keyboard_with_back_button(current_keyboard_layout: list[list[KeyboardButton]]):
    keyboard_layout = current_keyboard_layout + [[KeyboardButton(text="Назад")]]
    return ReplyKeyboardMarkup(keyboard=keyboard_layout, resize_keyboard=True)

def get_confirm_delete_org_keyboard(org_id: int):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, удалить", callback_data=f"confirm_delete_org_{org_id}"),
         InlineKeyboardButton(text="Отмена", callback_data="cancel_delete_org")]
    ], row_width=2)
    return keyboard

def get_confirm_assign_manager_keyboard(user_id: int):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, назначить", callback_data=f"confirm_assign_manager_{user_id}"),
         InlineKeyboardButton(text="Отмена", callback_data="cancel_assign_manager")]
    ], row_width=2)
    return keyboard

def get_confirm_assign_employee_keyboard(user_id: int):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, назначить", callback_data=f"confirm_assign_employee_{user_id}"),
         InlineKeyboardButton(text="Отмена", callback_data="cancel_assign_employee")]
    ], row_width=2)
    return keyboard

def get_users_for_assign_manager_keyboard(users: list):
    keyboard_layout = []
    for user in users:
        keyboard_layout.append([InlineKeyboardButton(text=f"{user['full_name']} (ID: {user['user_id']})", callback_data=f"select_user_assign_manager_{user['user_id']}")])
    keyboard_layout.append([InlineKeyboardButton(text="Назад", callback_data="cancel_action")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard_layout)

def get_managers_for_remove_keyboard(managers: list):
    keyboard_layout = []
    for manager in managers:
        org_info = f" (Орг ID: {manager['organization_id']})" if manager['organization_id'] else ""
        keyboard_layout.append([InlineKeyboardButton(text=f"{manager['full_name']} (ID: {manager['user_id']}){org_info}", callback_data=f"select_manager_remove_{manager['user_id']}")])
    keyboard_layout.append([InlineKeyboardButton(text="Назад", callback_data="cancel_action")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard_layout)

def get_users_for_assign_employee_keyboard(users: list):
    keyboard_layout = []
    for user in users:
        keyboard_layout.append([InlineKeyboardButton(text=f"{user['full_name']} (ID: {user['user_id']})", callback_data=f"select_user_assign_employee_{user['user_id']}")])
    keyboard_layout.append([InlineKeyboardButton(text="Назад", callback_data="cancel_action")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard_layout)

def get_employees_for_remove_keyboard(employees: list):
    keyboard_layout = []
    for employee in employees:
        keyboard_layout.append([InlineKeyboardButton(text=f"{employee['full_name']} (ID: {employee['user_id']})", callback_data=f"select_employee_remove_{employee['user_id']}")])
    keyboard_layout.append([InlineKeyboardButton(text="Назад", callback_data="cancel_action")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard_layout)

def get_employees_for_assign_task_keyboard(employees: list):
    keyboard_layout = []
    for employee in employees:
        keyboard_layout.append([InlineKeyboardButton(text=f"{employee['full_name']} (ID: {employee['user_id']})", callback_data=f"select_employee_assign_task_{employee['user_id']}")])
    keyboard_layout.append([InlineKeyboardButton(text="Назад", callback_data="cancel_action")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard_layout)

def get_organizations_for_assign_manager_keyboard(organizations) -> InlineKeyboardMarkup:
    keyboard = []
    for org in organizations:
        keyboard.append([InlineKeyboardButton(text=f"{org['name']} (ID: {org['org_id']})", callback_data=f"select_org_assign_manager_{org['org_id']}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="cancel_action")]) # Universal back button
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
