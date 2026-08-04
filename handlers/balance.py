from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
import database as db
from config import CLICK_CARD, PAYNET_CARD, ADMIN_CHAT_ID
from keyboards import BTN_TOPUP, BTN_BACK, main_menu_kb, back_only_kb, topup_methods_kb, admin_topup_kb
from states import TopUpStates

router = Router()

CARDS = {"click": CLICK_CARD, "paynet": PAYNET_CARD}
METHOD_NAMES = {"click": "Click", "paynet": "Paynet"}


@router.message(F.text == BTN_TOPUP)
async def topup_start(message: Message):
    await message.answer("Выберите способ пополнения:", reply_markup=topup_methods_kb())


@router.callback_query(F.data.startswith("topup:"))
async def topup_method(callback: CallbackQuery, state: FSMContext):
    method = callback.data.split(":")[1]
    card = CARDS[method]
    comment = f"TG-{callback.from_user.id}"
    await state.update_data(method=method)
    await state.set_state(TopUpStates.waiting_receipt)
    await callback.message.edit_text(
        f"💳 Пополнение через {METHOD_NAMES[method]}\n\n"
        f"Карта: {card}\n"
        f"Комментарий к платежу: {comment}\n\n"
        "⚠️ Обязательно указывайте этот комментарий при переводе — "
        "по нему мы найдём ваш платёж."
    )
    await callback.message.answer(
        "После оплаты отправьте сюда чек (фото).\n\n"
        "❗️ВАЖНО: на чеке должны быть чётко видны ДАТА, ВРЕМЯ и ОТ КОГО "
        "отправлен платёж — иначе мы не сможем зачислить средства.",
        reply_markup=back_only_kb(),
    )


@router.message(TopUpStates.waiting_receipt, F.text == BTN_BACK)
async def receipt_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu_kb())


@router.message(TopUpStates.waiting_receipt, F.photo)
async def receipt_received(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    method = data.get("method", "—")
    file_id = message.photo[-1].file_id
    topup_id = await db.create_topup(message.from_user.id, method, file_id)
    await state.clear()
    await message.answer(
        "✅ Чек получен и отправлен на проверку администратору.\n"
        "Баланс будет пополнен после подтверждения.",
        reply_markup=main_menu_kb(),
    )
    if ADMIN_CHAT_ID:
        await bot.send_photo(
            ADMIN_CHAT_ID,
            file_id,
            caption=(
                f"💰 Заявка на пополнение №{topup_id}\n"
                f"Пользователь: {message.from_user.id} (@{message.from_user.username})\n"
                f"Способ: {METHOD_NAMES.get(method, method)}\n\n"
                f"Проверьте сумму на чеке и нажмите «Принять» или «Отклонить»."
            ),
            reply_markup=admin_topup_kb(topup_id),
        )


@router.message(TopUpStates.waiting_receipt)
async def receipt_wrong_type(message: Message):
    await message.answer("❗️ Пожалуйста, отправьте чек именно фотографией (скриншотом).")
