import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

import app_context
import databases
from bot.channel_handlers import register as register_channel, register_payments
from bot.private_handlers import register as register_private, set_bot_commands
from telethon_runner import init_telethon


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    app_context.bot = bot

    init_telethon()
    databases.initialize()

    await set_bot_commands(bot)
    register_channel(dp)
    register_payments(dp)
    register_private(dp)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
