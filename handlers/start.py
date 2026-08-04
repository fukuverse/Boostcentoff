from aiogram import Router, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message
import database as db
from config import ADMIN_CHAT_ID
from keyboards import main_menu_kb, site_kb

router = Router()

WELCOME_TEXT = "👋 Добро пожаловать! Выберите действие в меню ниже."


async def _greet(message: Message, bot: Bot):
    is_new = await db.ensure_user(message.from_user.id, message.from_user.username)
    if await db.is_banned(message.from_user.id):
        await message.answer("⛔ Вы заблокированы за нарушение правил. Обратитесь в поддержку.")
        return
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb())
    await message.answer("🌐 Наш сайт:", reply_markup=site_kb())
    if is_new and ADMIN_CHAT_ID:
        try:
            await bot.send_message(
                ADMIN_CHAT_ID,
                f"🆕 Новый пользователь: {message.from_user.id} (@{message.from_user.username})",
            )
        except Exception:
            pass


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    await _greet(message, bot)
