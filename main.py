import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import MenuButtonWebApp, WebAppInfo
from config import BOT_TOKEN, SITE_URL
import database as db
from handlers import start, menu, orders, balance, admin

logging.basicConfig(level=logging.INFO)


async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(admin.router)   # админ-команды и кнопки выше остальных
    dp.include_router(start.router)
    dp.include_router(orders.router)
    dp.include_router(balance.router)
    dp.include_router(menu.router)

    await db.init_db()
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="🌐 Наш сайт", web_app=WebAppInfo(url=SITE_URL))
        )
        await dp.start_polling(bot)
    finally:
        await db.close_db()


if __name__ == "__main__":
    asyncio.run(main())
