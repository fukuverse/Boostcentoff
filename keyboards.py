from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from config import SITE_URL
from services import PLATFORM_NAMES, PLATFORM_SERVICES, SERVICE_LABELS, SERVICES

# ----------------------------------------------------------------- reply-меню
BTN_ORDER = "📦 Дать заказ"
BTN_NUMBER = "📱 Взять номер"
BTN_MY_ORDERS = "🧾 Мои заказы"
BTN_TOPUP = "💳 Пополнить счет"
BTN_BALANCE = "💰 Мой счет"
BTN_HELP = "❓ Помощь"
BTN_FREE_PROMO = "🆓 Бесплатное продвижение"
BTN_BACK = "⬅️ Назад"

# услуги, доступные в разделе "Бесплатное продвижение" (платформа -> {просмотры, лайки})
FREE_PROMO_SERVICES = {
    "tg": {"views": "tg_views", "reactions": "tg_reactions"},
    "ig": {"views": "ig_views", "reactions": "ig_reactions"},
}


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_ORDER), KeyboardButton(text=BTN_NUMBER)],
            [KeyboardButton(text=BTN_MY_ORDERS), KeyboardButton(text=BTN_TOPUP)],
            [KeyboardButton(text=BTN_BALANCE), KeyboardButton(text=BTN_HELP)],
            [KeyboardButton(text=BTN_FREE_PROMO)],
        ],
        resize_keyboard=True,
    )


def back_only_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_BACK)]], resize_keyboard=True
    )


# ----------------------------------------------------------------- бесплатное продвижение
def free_promo_platforms_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Telegram", callback_data="freeplat:tg")],
        [InlineKeyboardButton(text="Instagram", callback_data="freeplat:ig")],
        [InlineKeyboardButton(text=BTN_BACK, callback_data="nav:menu")],
    ])


def free_promo_services_kb(platform: str) -> InlineKeyboardMarkup:
    svc = FREE_PROMO_SERVICES[platform]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👁 Просмотры", callback_data=f"var:{svc['views']}:free")],
        [InlineKeyboardButton(text="❤️ Лайки", callback_data=f"var:{svc['reactions']}:free")],
        [InlineKeyboardButton(text=BTN_BACK, callback_data="nav:freepromo")],
    ])


# ----------------------------------------------------------------- сайт (инлайн-кнопка в главном меню)
def site_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🌐 Наш сайт", url=SITE_URL)]]
    )


# ----------------------------------------------------------------- выбор платформы
def platforms_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=name, callback_data=f"plat:{key}")]
            for key, name in PLATFORM_NAMES.items()]
    rows.append([InlineKeyboardButton(text=BTN_BACK, callback_data="nav:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def services_kb(platform: str) -> InlineKeyboardMarkup:
    rows = []
    for service_key in PLATFORM_SERVICES[platform]:
        rows.append([InlineKeyboardButton(
            text=SERVICE_LABELS[service_key], callback_data=f"srv:{service_key}"
        )])
    rows.append([InlineKeyboardButton(text=BTN_BACK, callback_data="nav:order")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def variants_kb(service_key: str) -> InlineKeyboardMarkup:
    # ВНИМАНИЕ: раздел "📦 Дать заказ" показывает только платные варианты.
    # Бесплатные услуги доступны исключительно через "🆓 Бесплатное продвижение".
    cfg = SERVICES[service_key]
    rows = []
    if "paid" in cfg:
        price = cfg["paid"]["price_per_1000"]
        rows.append([InlineKeyboardButton(
            text=f"💳 {cfg['paid']['label']} — {price} so'm",
            callback_data=f"var:{service_key}:paid",
        )])
    if "tiers" in cfg:
        for tier in cfg["tiers"]:
            rows.append([InlineKeyboardButton(
                text=f"{tier['label']} — {tier['price_per_1000']} so'm",
                callback_data=f"var:{service_key}:{tier['key']}",
            )])
    rows.append([InlineKeyboardButton(
        text=BTN_BACK, callback_data=f"nav:platform:{cfg['platform']}"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_action_kb(service_key: str, variant: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Дать заявку", callback_data=f"start_order:{service_key}:{variant}")],
        [InlineKeyboardButton(text=BTN_BACK, callback_data=f"nav:service:{service_key}")],
    ])


def confirm_order_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить", callback_data="confirm_order")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_order_draft")],
    ])


# ----------------------------------------------------------------- пополнение
def topup_methods_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Click", callback_data="topup:click")],
        [InlineKeyboardButton(text="Paynet", callback_data="topup:paynet")],
    ])


# ----------------------------------------------------------------- взять номер
def take_number_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Написать админу", url="https://t.me/boostcent")],
    ])


# ----------------------------------------------------------------- админ: заказ
# Финальные статусы — кнопки управления заказом больше не нужны и должны исчезать.
FINAL_ORDER_STATUSES = {"Сделано", "Отменено"}


def admin_order_kb(order_id: int, order_status: str | None = None) -> InlineKeyboardMarkup | None:
    """Кнопки управления заказом. Если заказ уже в финальном статусе
    (Сделано / Отменено) — кнопки не показываются (возвращается None)."""
    if order_status in FINAL_ORDER_STATUSES:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏳ В ожидании", callback_data=f"adm:pending:{order_id}"),
            InlineKeyboardButton(text="✅ Сделано", callback_data=f"adm:done:{order_id}"),
        ],
        [InlineKeyboardButton(text="🚫 Отменить и вернуть деньги", callback_data=f"adm:cancel:{order_id}")],
    ])


def admin_cancel_confirm_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, отменить заказ", callback_data=f"adm:cancelconfirm:{order_id}"),
            InlineKeyboardButton(text="⬅️ Нет, назад", callback_data=f"adm:cancelabort:{order_id}"),
        ],
    ])


def admin_ban_notice_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Разбанить", callback_data=f"adm:unban:{user_id}")],
    ])


# ----------------------------------------------------------------- админ: заявка на пополнение (чек)
def admin_topup_kb(topup_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"admtopup:approve:{topup_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admtopup:reject:{topup_id}"),
        ],
    ])


def admin_topup_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="admtopupconfirm:go"),
            InlineKeyboardButton(text="✏️ Ввести заново", callback_data="admtopupconfirm:retry"),
        ],
        [InlineKeyboardButton(text="🚫 Отмена", callback_data="admtopupconfirm:abort")],
    ])


# ----------------------------------------------------------------- админ-панель (главное меню)
def admin_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Заказы", callback_data="admord:platforms")],
        [InlineKeyboardButton(text="💳 Пополнения", callback_data="admtopups:list")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admstat:users")],
        [InlineKeyboardButton(text="💰 Финансы", callback_data="admstat:turnover")],
        [InlineKeyboardButton(text="🏆 Топ услуг", callback_data="admstat:top")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="broadcast:start")],
    ])


# ----------------------------------------------------------------- админ: заказы — платформа → услуга → список
def admin_order_platforms_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=name, callback_data=f"admordplat:{key}")]
            for key, name in PLATFORM_NAMES.items()]
    rows.append([InlineKeyboardButton(text=BTN_BACK, callback_data="admpanel:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_order_services_kb(platform: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="📂 Все услуги", callback_data=f"admordsvc:{platform}:all")]]
    for service_key in PLATFORM_SERVICES[platform]:
        rows.append([InlineKeyboardButton(
            text=SERVICE_LABELS[service_key], callback_data=f"admordsvc:{platform}:{service_key}"
        )])
    rows.append([InlineKeyboardButton(text=BTN_BACK, callback_data="admord:platforms")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_order_list_kb(platform: str, service_key: str, offset: int, status: str,
                         order_ids: list[int]) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for i, oid in enumerate(order_ids, 1):
        row.append(InlineKeyboardButton(
            text=f"№{oid}", callback_data=f"admorditem:{oid}:{platform}:{service_key}:{offset}:{status}"
        ))
        if i % 5 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(
            text="⬅️", callback_data=f"admordlist:{platform}:{service_key}:{max(0, offset-10)}:{status}"
        ))
    if len(order_ids) == 10:
        nav.append(InlineKeyboardButton(
            text="➡️", callback_data=f"admordlist:{platform}:{service_key}:{offset+10}:{status}"
        ))
    if nav:
        rows.append(nav)

    filters = [
        InlineKeyboardButton(
            text="• Все" if status == "all" else "Все",
            callback_data=f"admordlist:{platform}:{service_key}:0:all",
        ),
        InlineKeyboardButton(
            text="• В ожидании" if status == "pending" else "В ожидании",
            callback_data=f"admordlist:{platform}:{service_key}:0:pending",
        ),
    ]
    rows.append(filters)
    rows.append([InlineKeyboardButton(text=BTN_BACK, callback_data=f"admordplat:{platform}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_order_detail_kb(order_id: int, platform: str, service_key: str,
                           offset: int, list_status: str, order_status: str | None = None) -> InlineKeyboardMarkup:
    """list_status — фильтр списка (all/pending), по которому вернуться назад.
    order_status — реальный статус заказа (Сделано/Отменено скрывают кнопки управления)."""
    kb = admin_order_kb(order_id, order_status)
    rows = list(kb.inline_keyboard) if kb else []
    rows.append(
        [InlineKeyboardButton(text=BTN_BACK, callback_data=f"admordlist:{platform}:{service_key}:{offset}:{list_status}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_pending_topups_kb(topups: list) -> InlineKeyboardMarkup:
    rows = []
    for t in topups:
        rows.append([InlineKeyboardButton(
            text=f"№{t['id']} · {t['user_id']} · ✅", callback_data=f"admtopup:approve:{t['id']}"
        ), InlineKeyboardButton(
            text="❌", callback_data=f"admtopup:reject:{t['id']}"
        )])
    rows.append([InlineKeyboardButton(text=BTN_BACK, callback_data="admpanel:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def broadcast_target_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Одному пользователю", callback_data="bctarget:one")],
        [InlineKeyboardButton(text="📢 Всем пользователям", callback_data="bctarget:all")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admpanel:back")],
    ])


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить", callback_data="bcsend")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admpanel:back")],
    ])
