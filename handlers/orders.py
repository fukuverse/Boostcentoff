import logging
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
import database as db
from config import ADMIN_CHAT_ID, ORDERS_CHAT_ID
from keyboards import (
    BTN_ORDER, BTN_BACK, BTN_FREE_PROMO,
    BTN_NUMBER, BTN_MY_ORDERS, BTN_TOPUP, BTN_BALANCE, BTN_HELP,
    main_menu_kb, back_only_kb, platforms_kb, services_kb, variants_kb,
    order_action_kb, confirm_order_kb, admin_order_kb, admin_ban_notice_kb,
    free_promo_platforms_kb, free_promo_services_kb,
)
from states import OrderStates
from services import (
    PLATFORM_NAMES, get_variant_cfg, build_info_text, calc_price, validate_link, LINK_HINTS,
)
from utils import user_ref
from handlers.menu import take_number, my_orders, my_balance, help_start
from handlers.balance import topup_start

router = Router()

# защита от повторного нажатия "Отправить" (двойной тап создавал два заказа
# и списывал деньги дважды, т.к. проверка баланса и создание заказа не были атомарны)
_processing_confirm: set[int] = set()


async def _reject_if_banned(target, user_id: int) -> bool:
    if await db.is_banned(user_id):
        text = "⛔ Вы заблокированы за нарушение правил (некорректные данные). Обратитесь в поддержку."
        if isinstance(target, CallbackQuery):
            await target.answer(text, show_alert=True)
        else:
            await target.answer(text)
        return True
    return False


# ----------------------------------------------------------------- вход в раздел заказа
@router.message(F.text == BTN_ORDER)
async def order_start(message: Message):
    if await _reject_if_banned(message, message.from_user.id):
        return
    await message.answer("Выберите платформу:", reply_markup=platforms_kb())


@router.callback_query(F.data == "nav:menu")
async def nav_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("Главное меню:", reply_markup=main_menu_kb())


# ----------------------------------------------------------------- бесплатное продвижение
@router.message(F.text == BTN_FREE_PROMO)
async def free_promo_start(message: Message):
    if await _reject_if_banned(message, message.from_user.id):
        return
    await message.answer("🆓 Бесплатное продвижение — выберите платформу:", reply_markup=free_promo_platforms_kb())


@router.callback_query(F.data == "nav:freepromo")
async def nav_free_promo(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🆓 Бесплатное продвижение — выберите платформу:", reply_markup=free_promo_platforms_kb()
    )


@router.callback_query(F.data.startswith("freeplat:"))
async def choose_free_platform(callback: CallbackQuery):
    platform = callback.data.split(":")[1]
    await callback.message.edit_text(
        f"{PLATFORM_NAMES[platform]} — бесплатно, выберите:", reply_markup=free_promo_services_kb(platform)
    )


@router.callback_query(F.data == "nav:order")
async def nav_order(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Выберите платформу:", reply_markup=platforms_kb())


@router.callback_query(F.data.startswith("nav:platform:"))
async def nav_platform(callback: CallbackQuery, state: FSMContext):
    platform = callback.data.split(":")[2]
    await state.clear()
    await callback.message.edit_text(
        f"{PLATFORM_NAMES[platform]} — выберите услугу:", reply_markup=services_kb(platform)
    )


@router.callback_query(F.data.startswith("nav:service:"))
async def nav_service(callback: CallbackQuery, state: FSMContext):
    service_key = callback.data.split(":")[2]
    await state.clear()
    await callback.message.edit_text("Выберите вариант:", reply_markup=variants_kb(service_key))


# ----------------------------------------------------------------- платформа -> услуги
@router.callback_query(F.data.startswith("plat:"))
async def choose_platform(callback: CallbackQuery):
    platform = callback.data.split(":")[1]
    await callback.message.edit_text(
        f"{PLATFORM_NAMES[platform]} — выберите услугу:", reply_markup=services_kb(platform)
    )


# ----------------------------------------------------------------- услуга -> варианты
@router.callback_query(F.data.startswith("srv:"))
async def choose_service(callback: CallbackQuery):
    service_key = callback.data.split(":")[1]
    await callback.message.edit_text("Выберите вариант:", reply_markup=variants_kb(service_key))


# ----------------------------------------------------------------- вариант -> инфо + "дать заявку"
@router.callback_query(F.data.startswith("var:"))
async def choose_variant(callback: CallbackQuery):
    _, service_key, variant = callback.data.split(":")
    text = build_info_text(service_key, variant)

    if variant == "free":
        cfg = get_variant_cfg(service_key, variant)
        available, next_dt = await db.check_free_cooldown(
            callback.from_user.id, service_key, cfg["cooldown_days"]
        )
        if not available:
            await callback.answer(
                f"Бесплатное продвижение уже использовано.\n"
                f"Следующий раз доступно: {next_dt.strftime('%d.%m.%Y %H:%M')}",
                show_alert=True,
            )
            return

    await callback.message.edit_text(text, reply_markup=order_action_kb(service_key, variant))


# ----------------------------------------------------------------- начало ввода заказа
@router.callback_query(F.data.startswith("start_order:"))
async def start_order(callback: CallbackQuery, state: FSMContext):
    _, service_key, variant = callback.data.split(":")
    if await _reject_if_banned(callback, callback.from_user.id):
        return

    cfg = get_variant_cfg(service_key, variant)
    await state.update_data(service_key=service_key, variant=variant)
    await state.set_state(OrderStates.waiting_amount)

    await callback.message.delete()
    await callback.message.answer(
        f"Введите нужное количество (от {cfg['min']} до {cfg['max']}):",
        reply_markup=back_only_kb(),
    )


_MENU_INTERRUPT_TEXTS = {
    BTN_NUMBER, BTN_MY_ORDERS, BTN_TOPUP, BTN_BALANCE, BTN_HELP,
    BTN_ORDER, BTN_FREE_PROMO,
}


@router.message(OrderStates.waiting_amount, F.text.in_(_MENU_INTERRUPT_TEXTS))
@router.message(OrderStates.waiting_link, F.text.in_(_MENU_INTERRUPT_TEXTS))
async def interrupt_order_flow(message: Message, state: FSMContext):
    """Если пользователь на шаге ввода количества/ссылки нажал другую кнопку
    главного меню — раньше это воспринималось как неверный ввод. Теперь
    прерываем оформление заказа и сразу переходим в нужный раздел."""
    await state.clear()
    text = message.text
    if text == BTN_NUMBER:
        await take_number(message)
    elif text == BTN_MY_ORDERS:
        await my_orders(message)
    elif text == BTN_TOPUP:
        await topup_start(message)
    elif text == BTN_BALANCE:
        await my_balance(message)
    elif text == BTN_HELP:
        await help_start(message, state)
    elif text == BTN_ORDER:
        await order_start(message)
    elif text == BTN_FREE_PROMO:
        await free_promo_start(message)


@router.message(OrderStates.waiting_amount, F.text == BTN_BACK)
async def amount_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu_kb())


@router.message(OrderStates.waiting_amount)
async def amount_received(message: Message, state: FSMContext, bot: Bot):
    if await _reject_if_banned(message, message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    cfg = get_variant_cfg(data["service_key"], data["variant"])

    if not message.text.isdigit():
        result = await db.register_invalid_event(message.from_user.id)
        if result["banned"]:
            await _notify_ban(message, result, bot)
            await state.clear()
            return
        await message.answer("❗ Введите правильное число, без букв и символов.")
        return

    amount = int(message.text)
    if amount < cfg["min"] or amount > cfg["max"]:
        result = await db.register_invalid_event(message.from_user.id)
        if result["banned"]:
            await _notify_ban(message, result, bot)
            await state.clear()
            return
        await message.answer(
            f"❗ Введите правильное число от {cfg['min']} до {cfg['max']}."
        )
        return

    await state.update_data(amount=amount)
    await state.set_state(OrderStates.waiting_link)
    await message.answer(LINK_HINTS.get(cfg["link_type"], "Отправьте ссылку:"))


@router.message(OrderStates.waiting_link, F.text == BTN_BACK)
async def link_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu_kb())


@router.message(OrderStates.waiting_link)
async def link_received(message: Message, state: FSMContext, bot: Bot):
    if await _reject_if_banned(message, message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    cfg = get_variant_cfg(data["service_key"], data["variant"])
    link = message.text.strip()

    if not validate_link(cfg["link_type"], link):
        result = await db.register_invalid_event(message.from_user.id)
        if result["banned"]:
            await _notify_ban(message, result, bot)
            await state.clear()
            return
        await message.answer(
            "❗ Ссылка указана неверно.\n" + LINK_HINTS.get(cfg["link_type"], "")
        )
        return

    price = calc_price(cfg["price_per_1000"], data["amount"])

    if price > 0:
        balance = await db.get_balance(message.from_user.id)
        if balance < price:
            await message.answer(
                f"❗ Недостаточно средств на балансе.\n"
                f"Нужно: {price} so'm, у вас: {balance} so'm.\n"
                f"Пополните счёт и попробуйте снова.",
                reply_markup=main_menu_kb(),
            )
            await state.clear()
            return

    await state.update_data(link=link, price=price)
    await state.set_state(OrderStates.confirm)

    price_text = "бесплатно" if price == 0 else f"{price} so'm"
    summary = (
        f"<b>Проверьте данные заказа:</b>\n\n"
        f"Услуга: {cfg['service_title']} — {cfg['label']}\n"
        f"Количество: {data['amount']}\n"
        f"Ссылка: {link}\n"
        f"Стоимость: {price_text}\n\n"
        f"Если все данные верны, нажмите «Отправить»."
    )
    await message.answer(summary, reply_markup=confirm_order_kb())


@router.callback_query(F.data == "cancel_order_draft")
async def cancel_order_draft(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("Заказ отменён. Главное меню:", reply_markup=main_menu_kb())


@router.callback_query(F.data == "confirm_order")
async def confirm_order(callback: CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id

    if user_id in _processing_confirm:
        # уже обрабатывается предыдущее нажатие той же кнопки — игнорируем повтор
        await callback.answer("Заявка уже обрабатывается, подождите…", show_alert=True)
        return
    _processing_confirm.add(user_id)
    try:
        data = await state.get_data()
        if not data or "service_key" not in data:
            # состояние уже очищено (например, предыдущим тапом) — заявка либо
            # уже создана, либо истекла; повторно ничего не делаем
            await callback.answer("Эта заявка уже оформлена или устарела.", show_alert=True)
            return

        cfg = get_variant_cfg(data["service_key"], data["variant"])

        if data["price"] > 0:
            balance = await db.get_balance(user_id)
            if balance < data["price"]:
                await callback.answer("Недостаточно средств.", show_alert=True)
                await state.clear()
                return
            await db.change_balance(user_id, -data["price"], reason=f"Заказ: {cfg['service_title']}")
        else:
            await db.mark_free_used(user_id, data["service_key"])

        order_id = await db.create_order(
            user_id=user_id,
            platform=cfg["platform"],
            service_key=data["service_key"],
            variant=data["variant"],
            amount=data["amount"],
            link=data["link"],
            price=data["price"],
        )

        await state.clear()
        await callback.message.delete()
        await callback.message.answer(
            f"✅ Заявка №{order_id} создана и передана в обработку.",
            reply_markup=main_menu_kb(),
        )

        if ORDERS_CHAT_ID:
            price_text = "бесплатно" if data["price"] == 0 else f"{data['price']} so'm"
            try:
                await bot.send_message(
                    ORDERS_CHAT_ID,
                    f"📦 <b>Новая заявка №{order_id}</b>\n"
                    f"Пользователь: {user_ref(user_id, callback.from_user.username)}\n"
                    f"Платформа: {PLATFORM_NAMES[cfg['platform']]}\n"
                    f"Услуга: {cfg['service_title']} — {cfg['label']}\n"
                    f"Количество: {data['amount']}\n"
                    f"Ссылка: {data['link']}\n"
                    f"Стоимость: {price_text}",
                    reply_markup=admin_order_kb(order_id, "В ожидании"),
                )
            except Exception:
                logging.exception("Не удалось отправить заявку №%s в ORDERS_CHAT_ID", order_id)
    finally:
        _processing_confirm.discard(user_id)


async def _notify_ban(message: Message, result: dict, bot: Bot):
    if result["permanent"]:
        await message.answer(
            "⛔ Вы заблокированы навсегда за повторные некорректные данные.\n"
            "Обратитесь в поддержку для разблокировки.",
            reply_markup=main_menu_kb(),
        )
    else:
        until = result["until"].strftime("%H:%M")
        await message.answer(
            f"⛔ Вы временно заблокированы до {until} за многократный ввод некорректных данных.\n"
            f"При повторном нарушении блокировка станет постоянной.",
            reply_markup=main_menu_kb(),
        )
    if ADMIN_CHAT_ID:
        kind = "постоянно" if result["permanent"] else f"до {result['until'].strftime('%d.%m %H:%M')}"
        try:
            await bot.send_message(
                ADMIN_CHAT_ID,
                f"🚫 Пользователь {user_ref(message.from_user.id, message.from_user.username)} "
                f"заблокирован {kind} за спам некорректными данными.",
                reply_markup=admin_ban_notice_kb(message.from_user.id),
            )
        except Exception:
            logging.exception("Не удалось отправить уведомление о бане в ADMIN_CHAT_ID")
