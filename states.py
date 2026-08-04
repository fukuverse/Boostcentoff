from aiogram.fsm.state import State, StatesGroup


class OrderStates(StatesGroup):
    waiting_amount = State()
    waiting_link = State()
    confirm = State()


class TopUpStates(StatesGroup):
    waiting_receipt = State()


class HelpStates(StatesGroup):
    waiting_message = State()


class BroadcastStates(StatesGroup):
    waiting_target = State()   # admin выбирает: одному / всем
    waiting_user_id = State()  # если одному — вводит id
    waiting_text = State()     # текст рассылки
    confirm = State()


class AdminTopupStates(StatesGroup):
    waiting_amount = State()   # админ вводит сумму зачисления после нажатия "Принять"
    confirm_amount = State()   # подтверждение суммы перед начислением
    waiting_reason = State()   # админ вводит причину после нажатия "Отклонить"
    confirm_reason = State()   # подтверждение причины перед отклонением


class AdminOrderStates(StatesGroup):
    waiting_cancel_reason = State()   # админ вводит причину отмены заказа (после подтверждения)
