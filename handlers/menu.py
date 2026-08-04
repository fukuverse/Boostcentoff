from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
import database as db
from config import ADMIN_CHAT_ID
from keyboards import (
    BTN_ORDER, BTN_NUMBER, BTN_MY_ORDERS, BTN_TOPUP, BTN_BALANCE, BTN_HELP, BTN_BACK,
    main_menu_kb, back_only_kb, platforms_kb, take_number_kb,
)
from states import HelpStates

router = Router()


@router.message(F.text == BTN_NUMBER)
async def take_number(message: Message):
    await message.answer(
        "📱 Вы можете оформить номер через администратора.\n"
        "Функция автоматического добавления номера скоро будет доступна.",
        reply_markup=take_number_kb(),
    )


@router.message(F.text == BTN_MY_ORDERS)
async def my_orders(message: Message):
    orders = await db.get_user_orders(message.from_user.id)
    if not orders:
        await message.answer("У вас пока нет заказов.")
        return
    lines = ["🧾 <b>Ваши заказы:</b>\n"]
    for o in orders:
        lines.append(
            f"№{o['id']} — {o['platform'].upper()} / {o['service_key']} "
            f"({o['amount']} шт.) — {o['price']} so'm — <b>{o['status']}</b>"
        )
    await message.answer("\n".join(lines))


@router.message(F.text == BTN_BALANCE)
async def my_balance(message: Message):
    balance = await db.get_balance(message.from_user.id)
    await message.answer(f"💰 Ваш баланс: <b>{balance} so'm</b>")


@router.message(F.text == BTN_HELP)
async def help_start(message: Message, state: FSMContext):
    await state.set_state(HelpStates.waiting_message)
    await message.answer(
        "❓ Опишите ваш вопрос или проблему одним сообщением — мы передадим его администратору.",
        reply_markup=back_only_kb(),
    )


@router.message(HelpStates.waiting_message, F.text == BTN_BACK)
async def help_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu_kb())


@router.message(HelpStates.waiting_message)
async def help_received(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    await message.answer("✅ Ваше сообщение отправлено администратору. Ожидайте ответа.",
                          reply_markup=main_menu_kb())
    if ADMIN_CHAT_ID:
        try:
            await bot.send_message(
                ADMIN_CHAT_ID,
                f"❓ Вопрос от пользователя {message.from_user.id} (@{message.from_user.username}):\n\n"
                f"{message.text}\n\n"
                f"Ответить: /reply {message.from_user.id} текст_ответа",
            )
        except Exception:
            pass
