from aiogram.fsm.state import State, StatesGroup

class RegistrationStates(StatesGroup):
    waiting_for_full_name = State()

class AdminStates(StatesGroup):
    waiting_for_org_name_to_create = State()
    waiting_for_org_name_to_delete = State()
    waiting_for_manager_id = State()
    waiting_for_manager_org_id = State()
    waiting_for_manager_id_to_remove = State()

class ManagerStates(StatesGroup):
    waiting_for_employee_id = State()
    waiting_for_task_title = State()
    waiting_for_task_description = State()
    waiting_for_employee_id_to_assign_task = State()
    waiting_for_employee_id_to_remove = State()

class EmployeeStates(StatesGroup):
    waiting_for_task_to_change_status = State()
