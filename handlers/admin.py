from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
import database as db
from config import ADMIN_CHAT_ID, ORDERS_CHAT_ID, MIN_TOPUP_AMOUNT
from keyboards import (
    admin_order_kb, admin_panel_kb, admin_ban_notice_kb,
    admin_cancel_confirm_kb,
    broadcast_target_kb, broadcast_confirm_kb,
    admin_pending_topups_kb, admin_topup_confirm_kb,
    admin_order_platforms_kb, admin_order_services_kb, admin_order_list_kb, admin_order_detail_kb,
)
from services import PLATFORM_NAMES, SERVICE_LABELS
from states import BroadcastStates, AdminTopupStates, AdminOrderStates

router = Router()


def _is_admin_chat(chat_id: int) -> bool:
    return bool(ADMIN_CHAT_ID) and chat_id == ADMIN_CHAT_ID


def _is_order_action_chat(chat_id: int) -> bool:
    """Кнопки статуса заказа (⏳/✅/🚫) показываются в ORDERS_CHAT_ID (канал заявок),
    а не в ADMIN_CHAT_ID — эта проверка разрешает управлять заказом из обоих чатов."""
    return _is_admin_chat(chat_id) or (bool(ORDERS_CHAT_ID) and chat_id == ORDERS_CHAT_ID)


# ================================================================= команды
@router.message(Command("panel"))
@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not _is_admin_chat(message.chat.id):
        return
    await message.answer("🛠 Админ-панель:", reply_markup=admin_panel_kb())


@router.message(Command("topup"))
async def admin_topup(message: Message, bot: Bot):
    if not _is_admin_chat(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].lstrip("-").isdigit():
        await message.answer("Использование: /topup user_id сумма")
        return
    user_id, amount = int(parts[1]), int(parts[2])
    new_balance = await db.change_balance(
        user_id, amount, admin_id=message.from_user.id, reason="Пополнение по чеку"
    )
    await message.answer(f"✅ Начислено {amount} so'm пользователю {user_id}. Баланс: {new_balance} so'm")
    try:
        await bot.send_message(
            user_id,
            f"✅ Ваш баланс пополнен на {amount} so'm.\nТекущий баланс: {new_balance} so'm",
        )
    except Exception:
        pass


# ================================================================= пополнение по чеку: принять / отклонить
@router.message(Command("reply"))
async def admin_reply(message: Message, bot: Bot):
    if not _is_admin_chat(message.chat.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) != 3 or not parts[1].isdigit():
        await message.answer("Использование: /reply user_id текст")
        return
    user_id, text = int(parts[1]), parts[2]
    try:
        await bot.send_message(user_id, f"💬 Ответ от поддержки:\n\n{text}")
        await message.answer("✅ Отправлено.")
    except Exception:
        await message.answer("❌ Не удалось отправить сообщение (пользователь мог заблокировать бота).")


@router.callback_query(F.data.startswith("admtopup:"))
async def admin_topup_action(callback: CallbackQuery, state: FSMContext):
    if not _is_admin_chat(callback.message.chat.id):
        return
    _, action, topup_id_s = callback.data.split(":")
    topup_id = int(topup_id_s)

    topup = await db.get_topup(topup_id)
    if not topup:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return
    if topup["status"] != "В ожидании":
        await callback.answer(f"Заявка уже обработана: {topup['status']}", show_alert=True)
        return

    await state.update_data(
        topup_id=topup_id,
        msg_chat_id=callback.message.chat.id,
        msg_id=callback.message.message_id,
    )

    if action == "approve":
        await state.set_state(AdminTopupStates.waiting_amount)
        await callback.answer()
        await callback.message.reply(
            f"Введите сумму зачисления для заявки №{topup_id} (пользователь {topup['user_id']}).\n"
            f"Для отмены — /cancel"
        )
    else:
        await state.set_state(AdminTopupStates.waiting_reason)
        await callback.answer()
        await callback.message.reply(
            f"Введите причину отклонения заявки №{topup_id} (пользователь {topup['user_id']}).\n"
            f"Для отмены — /cancel"
        )


@router.message(Command("cancel"), AdminTopupStates.waiting_amount)
@router.message(Command("cancel"), AdminTopupStates.confirm_amount)
@router.message(Command("cancel"), AdminTopupStates.waiting_reason)
@router.message(Command("cancel"), AdminTopupStates.confirm_reason)
@router.message(Command("cancel"), AdminOrderStates.waiting_cancel_reason)
async def admin_topup_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.")


@router.message(AdminTopupStates.waiting_amount)
async def admin_topup_amount(message: Message, state: FSMContext):
    if not _is_admin_chat(message.chat.id):
        return
    if not message.text or not message.text.isdigit():
        await message.answer("❗ Введите сумму числом (только цифры, без пробелов и ID), либо /cancel для отмены.")
        return

    amount = int(message.text)
    if amount < MIN_TOPUP_AMOUNT:
        await message.answer(f"❗ Сумма меньше минимальной ({MIN_TOPUP_AMOUNT} so'm). Введите другую сумму.")
        return

    data = await state.get_data()
    topup_id = data["topup_id"]
    topup = await db.get_topup(topup_id)
    if not topup or topup["status"] != "В ожидании":
        await message.answer("Эта заявка уже обработана.")
        await state.clear()
        return

    await state.update_data(kind="credit", amount=amount)
    await state.set_state(AdminTopupStates.confirm_amount)
    await message.answer(
        f"Подтвердите:\nНачислить <b>{amount} so'm</b> пользователю {topup['user_id']} "
        f"(заявка №{topup_id})?",
        reply_markup=admin_topup_confirm_kb(),
    )


@router.message(AdminTopupStates.waiting_reason)
async def admin_topup_reason(message: Message, state: FSMContext):
    if not _is_admin_chat(message.chat.id):
        return
    if not message.text:
        await message.answer("❗ Введите текст причины (или /cancel для отмены).")
        return
    reason = message.text.strip()

    data = await state.get_data()
    topup_id = data["topup_id"]
    topup = await db.get_topup(topup_id)
    if not topup or topup["status"] != "В ожидании":
        await message.answer("Эта заявка уже обработана.")
        await state.clear()
        return

    await state.update_data(kind="reject", reason=reason)
    await state.set_state(AdminTopupStates.confirm_reason)
    await message.answer(
        f"Подтвердите:\nОтклонить заявку №{topup_id} (пользователь {topup['user_id']}) с причиной:\n"
        f"«{reason}»?",
        reply_markup=admin_topup_confirm_kb(),
    )


@router.callback_query(F.data.startswith("admtopupconfirm:"))
async def admin_topup_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not _is_admin_chat(callback.message.chat.id):
        return
    action = callback.data.split(":")[1]
    data = await state.get_data()
    kind = data.get("kind")

    if action == "abort":
        await state.clear()
        await callback.answer()
        await callback.message.edit_text("🚫 Отменено.")
        return

    if action == "retry":
        await callback.answer()
        if kind == "credit":
            await state.set_state(AdminTopupStates.waiting_amount)
            await callback.message.edit_text(
                f"Введите сумму зачисления для заявки №{data.get('topup_id')} заново.\nДля отмены — /cancel"
            )
        else:
            await state.set_state(AdminTopupStates.waiting_reason)
            await callback.message.edit_text(
                f"Введите причину отклонения для заявки №{data.get('topup_id')} заново.\nДля отмены — /cancel"
            )
        return

    # action == "go"
    topup_id = data.get("topup_id")
    topup = await db.get_topup(topup_id)
    if not topup or topup["status"] != "В ожидании":
        await callback.answer("Заявка уже обработана.", show_alert=True)
        await state.clear()
        return

    if kind == "credit":
        amount = data["amount"]
        new_balance = await db.change_balance(
            topup["user_id"], amount, admin_id=callback.from_user.id,
            reason=f"Пополнение по чеку №{topup_id}",
        )
        ok = await db.set_topup_status(topup_id, "Принято", amount)
        if not ok:
            await db.change_balance(
                topup["user_id"], -amount, admin_id=callback.from_user.id,
                reason=f"Откат: заявка №{topup_id} уже была обработана",
            )
            await callback.answer("Заявка уже была обработана другим способом. Начисление отменено.", show_alert=True)
            await state.clear()
            return

        await callback.answer("Зачислено ✅")
        await callback.message.edit_text(
            f"✅ Заявка №{topup_id} принята.\nНачислено {amount} so'm пользователю {topup['user_id']}.\n"
            f"Баланс: {new_balance} so'm"
        )

        try:
            await bot.edit_message_caption(
                chat_id=data["msg_chat_id"], message_id=data["msg_id"],
                caption=f"💰 Заявка на пополнение №{topup_id}\n\n✅ Принято, начислено {amount} so'm",
            )
        except Exception:
            pass

        try:
            await bot.send_message(
                topup["user_id"],
                f"✅ Ваш счёт пополнен на {amount} so'm.\nТекущий баланс: {new_balance} so'm",
            )
        except Exception:
            await callback.message.answer(
                "⚠️ Деньги начислены, но сообщение клиенту не доставлено "
                "(возможно, он заблокировал бота)."
            )

    else:  # reject
        reason = data["reason"]
        ok = await db.set_topup_status(topup_id, "Отклонено")
        if not ok:
            await callback.answer("Заявка уже была обработана другим способом.", show_alert=True)
            await state.clear()
            return

        await callback.answer("Отклонено ❌")
        await callback.message.edit_text(
            f"❌ Заявка №{topup_id} отклонена.\nПричина: {reason}"
        )

        try:
            await bot.edit_message_caption(
                chat_id=data["msg_chat_id"], message_id=data["msg_id"],
                caption=f"💰 Заявка на пополнение №{topup_id}\n\n❌ Отклонено\nПричина: {reason}",
            )
        except Exception:
            pass

        try:
            await bot.send_message(
                topup["user_id"],
                f"❌ Ваш чек на пополнение отклонён.\nПричина: {reason}\n\n"
                f"Если считаете это ошибкой — напишите в поддержку.",
            )
        except Exception:
            await callback.message.answer(
                "⚠️ Заявка отклонена, но сообщение клиенту не доставлено "
                "(возможно, он заблокировал бота)."
            )

    await state.clear()


@router.callback_query(F.data == "admtopups:list")
async def admin_topups_list(callback: CallbackQuery):
    if not _is_admin_chat(callback.message.chat.id):
        return
    topups = await db.get_pending_topups(limit=15)
    total = await db.count_pending_topups()
    if not topups:
        await callback.message.edit_text(
            "Заявок на пополнение в ожидании нет.", reply_markup=admin_panel_kb()
        )
        return
    text = (
        f"💳 <b>Заявки на пополнение</b> (в ожидании: {total})\n\n"
        f"Чек для каждой заявки был отправлен отдельным сообщением выше в этом чате — "
        f"пролистайте историю, чтобы свериться с фото.\n\n"
        f"Нажмите ✅, чтобы принять (потребуется ввести сумму), или ❌, чтобы отклонить (потребуется причина)."
    )
    await callback.message.edit_text(text, reply_markup=admin_pending_topups_kb(topups))


# ================================================================= статус заказа / отмена с возвратом
@router.callback_query(F.data.startswith("adm:"))
async def admin_order_status(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not _is_order_action_chat(callback.message.chat.id):
        return
    parts = callback.data.split(":")
    action, order_id = parts[1], int(parts[2])

    if action == "unban":
        await db.unban_user(order_id)  # тут order_id на самом деле user_id (см. admin_ban_notice_kb)
        await callback.answer("Пользователь разбанен.")
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        try:
            await bot.send_message(order_id, "✅ Вы разблокированы администратором. Можете пользоваться ботом.")
        except Exception:
            pass
        return

    order = await db.get_order(order_id)
    if not order:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    # -------- отмена: требует подтверждения и причины, деньги возвращаются только после этого
    if action == "cancel":
        if order["status"] in ("Сделано", "Отменено"):
            await callback.answer(f"Заказ уже в статусе «{order['status']}», отмена недоступна.", show_alert=True)
            return
        await callback.answer()
        try:
            await callback.message.edit_reply_markup(reply_markup=admin_cancel_confirm_kb(order_id))
        except Exception:
            pass
        return

    if action == "cancelabort":
        await callback.answer("Отмена заказа прервана.")
        try:
            await callback.message.edit_reply_markup(reply_markup=admin_order_kb(order_id, order["status"]))
        except Exception:
            pass
        return

    if action == "cancelconfirm":
        if order["status"] in ("Сделано", "Отменено"):
            await callback.answer(f"Заказ уже в статусе «{order['status']}», отмена недоступна.", show_alert=True)
            try:
                await callback.message.edit_reply_markup(reply_markup=admin_order_kb(order_id, order["status"]))
            except Exception:
                pass
            return
        await state.set_state(AdminOrderStates.waiting_cancel_reason)
        await state.update_data(
            order_id=order_id,
            msg_chat_id=callback.message.chat.id,
            msg_id=callback.message.message_id,
        )
        await callback.answer()
        await callback.message.reply(
            f"Напишите причину отмены заказа №{order_id} (пользователь получит её в сообщении).\n"
            f"Для отмены действия — /cancel"
        )
        return

    # -------- пополнение статусов "В ожидании" / "Сделано"
    status = "В ожидании" if action == "pending" else "Сделано"
    await db.set_order_status(order_id, status)

    await callback.answer(f"Статус заявки №{order_id}: {status}")
    try:
        await callback.message.edit_reply_markup(reply_markup=admin_order_kb(order_id, status))
    except Exception:
        pass
    try:
        await bot.send_message(order["user_id"], f"ℹ️ Статус вашей заявки №{order_id} изменён: {status}")
    except Exception:
        pass


@router.message(AdminOrderStates.waiting_cancel_reason)
async def admin_order_cancel_reason(message: Message, state: FSMContext, bot: Bot):
    if not _is_order_action_chat(message.chat.id):
        return
    if not message.text:
        await message.answer("❗ Введите текст причины отмены (или /cancel для отмены действия).")
        return
    reason = message.text.strip()

    data = await state.get_data()
    order_id = data["order_id"]
    order = await db.get_order(order_id)
    if not order:
        await message.answer("Заказ не найден.")
        await state.clear()
        return
    if order["status"] in ("Сделано", "Отменено"):
        await message.answer(f"Заказ уже в статусе «{order['status']}», отмена недоступна.")
        await state.clear()
        return

    await db.set_order_status(order_id, "Отменено")
    if order["price"] > 0:
        await db.change_balance(
            order["user_id"], order["price"],
            admin_id=message.from_user.id, reason=f"Возврат за отменённый заказ №{order_id}: {reason}",
        )

    await message.answer(f"🚫 Заказ №{order_id} отменён. Причина: {reason}")

    try:
        await bot.edit_message_reply_markup(
            chat_id=data["msg_chat_id"], message_id=data["msg_id"], reply_markup=None,
        )
    except Exception:
        pass

    try:
        text = f"ℹ️ Статус вашей заявки №{order_id} изменён: Отменено\nПричина: {reason}"
        if order["price"] > 0:
            text += f"\n💰 Средства ({order['price']} so'm) возвращены на баланс."
        await bot.send_message(order["user_id"], text)
    except Exception:
        pass

    await state.clear()


# ================================================================= статистика
@router.callback_query(F.data == "admpanel:back")
async def admpanel_back(callback: CallbackQuery, state: FSMContext):
    if not _is_admin_chat(callback.message.chat.id):
        return
    await state.clear()
    await callback.message.edit_text("🛠 Админ-панель:", reply_markup=admin_panel_kb())


@router.callback_query(F.data.startswith("admstat:"))
async def admin_stats(callback: CallbackQuery):
    if not _is_admin_chat(callback.message.chat.id):
        return
    kind = callback.data.split(":")[1]

    if kind == "users":
        s = await db.stats_users()
        text = (
            f"📊 <b>Пользователи</b>\n\n"
            f"Всего: {s['total']}\n"
            f"Новых за сутки: {s['today']}\n"
            f"Заблокировано: {s['banned']}"
        )
    elif kind == "turnover":
        s = await db.stats_turnover()
        text = (
            f"📊 <b>Обороты</b>\n\n"
            f"Списано за заказы: {s['spent']} so'm\n"
            f"Начислено пополнений: {s['topped_up']} so'm"
        )
    else:  # top
        rows = await db.stats_top_services()
        if not rows:
            text = "📊 <b>Топ услуг</b>\n\nПока нет заказов."
        else:
            lines = ["📊 <b>Топ услуг</b>\n"]
            for r in rows:
                label = SERVICE_LABELS.get(r["service_key"], r["service_key"])
                lines.append(f"{label} — {r['cnt']} заказ(ов)")
            text = "\n".join(lines)

    await callback.message.edit_text(text, reply_markup=admin_panel_kb())


# ================================================================= заказы: платформа → услуга → список
@router.callback_query(F.data == "admord:platforms")
async def admord_platforms(callback: CallbackQuery):
    if not _is_admin_chat(callback.message.chat.id):
        return
    s = await db.stats_orders()
    text = (
        f"📦 <b>Заказы</b>\n\n"
        f"Всего: {s['total']} · В ожидании: {s['pending']} · "
        f"Сделано: {s['done']} · Отменено: {s['cancelled']}\n\n"
        f"Выберите платформу:"
    )
    await callback.message.edit_text(text, reply_markup=admin_order_platforms_kb())


@router.callback_query(F.data.startswith("admordplat:"))
async def admordplat(callback: CallbackQuery):
    if not _is_admin_chat(callback.message.chat.id):
        return
    platform = callback.data.split(":")[1]
    plat_name = PLATFORM_NAMES.get(platform, platform)
    await callback.message.edit_text(
        f"{plat_name} — выберите услугу:", reply_markup=admin_order_services_kb(platform)
    )


async def _render_order_list(callback: CallbackQuery, platform: str, service_key: str, offset: int, status: str):
    db_status = None if status == "all" else "В ожидании"
    db_service = None if service_key == "all" else service_key

    orders = await db.get_orders_page(
        offset=offset, limit=10, status=db_status, platform=platform, service_key=db_service
    )
    total = await db.count_orders(status=db_status, platform=platform, service_key=db_service)

    plat_name = PLATFORM_NAMES.get(platform, platform)
    svc_name = "Все услуги" if service_key == "all" else SERVICE_LABELS.get(service_key, service_key)

    if not orders:
        text = f"🧾 <b>{plat_name} — {svc_name}</b>\n\nЗаказов не найдено."
    else:
        text = f"🧾 <b>{plat_name} — {svc_name}</b> (всего: {total})\nВыберите заказ:"
    order_ids = [o["id"] for o in orders]
    await callback.message.edit_text(
        text, reply_markup=admin_order_list_kb(platform, service_key, offset, status, order_ids)
    )


@router.callback_query(F.data.startswith("admordsvc:"))
async def admordsvc(callback: CallbackQuery):
    if not _is_admin_chat(callback.message.chat.id):
        return
    _, platform, service_key = callback.data.split(":")
    await _render_order_list(callback, platform, service_key, 0, "all")


@router.callback_query(F.data.startswith("admordlist:"))
async def admordlist(callback: CallbackQuery):
    if not _is_admin_chat(callback.message.chat.id):
        return
    _, platform, service_key, offset, status = callback.data.split(":")
    await _render_order_list(callback, platform, service_key, int(offset), status)


@router.callback_query(F.data.startswith("admorditem:"))
async def admorditem(callback: CallbackQuery):
    if not _is_admin_chat(callback.message.chat.id):
        return
    _, order_id, platform, service_key, offset, status = callback.data.split(":")
    order_id, offset = int(order_id), int(offset)
    order = await db.get_order(order_id)
    if not order:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    platform_name = PLATFORM_NAMES.get(order["platform"], order["platform"])
    service_label = SERVICE_LABELS.get(order["service_key"], order["service_key"])
    price_text = "бесплатно" if order["price"] == 0 else f"{order['price']} so'm"

    text = (
        f"<b>Заявка №{order['id']}</b>\n\n"
        f"Пользователь: {order['user_id']}\n"
        f"Платформа: {platform_name}\n"
        f"Услуга: {service_label} ({order['variant']})\n"
        f"Количество: {order['amount']}\n"
        f"Ссылка: {order['link']}\n"
        f"Стоимость: {price_text}\n"
        f"Статус: {order['status']}\n"
        f"Создан: {order['created_at'].strftime('%d.%m.%Y %H:%M')}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=admin_order_detail_kb(
            order_id, platform, service_key, offset, status, order_status=order["status"]
        ),
    )


# ================================================================= рассылка
@router.callback_query(F.data == "broadcast:start")
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    if not _is_admin_chat(callback.message.chat.id):
        return
    await state.set_state(BroadcastStates.waiting_target)
    await callback.message.edit_text(
        "📢 Кому отправить рассылку?", reply_markup=broadcast_target_kb()
    )


@router.callback_query(BroadcastStates.waiting_target, F.data.startswith("bctarget:"))
async def broadcast_target(callback: CallbackQuery, state: FSMContext):
    if not _is_admin_chat(callback.message.chat.id):
        return
    target = callback.data.split(":")[1]
    await state.update_data(target=target)
    if target == "one":
        await state.set_state(BroadcastStates.waiting_user_id)
        await callback.message.edit_text("Введите ID пользователя:")
    else:
        await state.set_state(BroadcastStates.waiting_text)
        await callback.message.edit_text("Введите текст рассылки для всех пользователей:")


@router.message(BroadcastStates.waiting_user_id)
async def broadcast_user_id(message: Message, state: FSMContext):
    if not _is_admin_chat(message.chat.id):
        return
    if not message.text.isdigit():
        await message.answer("❗ Введите числовой ID пользователя.")
        return
    await state.update_data(user_id=int(message.text))
    await state.set_state(BroadcastStates.waiting_text)
    await message.answer("Введите текст сообщения:")


@router.message(BroadcastStates.waiting_text)
async def broadcast_text(message: Message, state: FSMContext):
    if not _is_admin_chat(message.chat.id):
        return
    await state.update_data(text=message.text)
    await state.set_state(BroadcastStates.confirm)
    data = await state.get_data()
    target_desc = f"пользователю {data['user_id']}" if data["target"] == "one" else "всем пользователям"
    await message.answer(
        f"Проверьте текст рассылки ({target_desc}):\n\n{message.text}",
        reply_markup=broadcast_confirm_kb(),
    )


@router.callback_query(BroadcastStates.confirm, F.data == "bcsend")
async def broadcast_send(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not _is_admin_chat(callback.message.chat.id):
        return
    data = await state.get_data()
    text = data["text"]

    if data["target"] == "one":
        try:
            await bot.send_message(data["user_id"], text)
            await callback.message.edit_text("✅ Сообщение отправлено.")
        except Exception:
            await callback.message.edit_text("❌ Не удалось отправить (пользователь заблокировал бота).")
    else:
        user_ids = await db.get_all_user_ids()
        sent, failed = 0, 0
        for uid in user_ids:
            try:
                await bot.send_message(uid, text)
                sent += 1
            except Exception:
                failed += 1
        await callback.message.edit_text(f"✅ Рассылка завершена.\nДоставлено: {sent}\nНе доставлено: {failed}")

    await state.clear()
