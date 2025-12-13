import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from dotenv import load_dotenv

import app_context
from data import databases
from bot.channel_handlers import register as register_channel, register_payments
from bot.private_handlers import register as register_private, set_bot_commands
from telethon_runner import init_telethon

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE")  
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH")  # optional; defaults to /webhook/<token>
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
WEBHOOK_PORT = int(os.getenv("PORT", os.getenv("WEBHOOK_PORT", 8080)))
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")


def _webhook_path() -> str:
    if WEBHOOK_PATH:
        return WEBHOOK_PATH
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")
    return f"/webhook/{BOT_TOKEN}"


def _webhook_url() -> str:
    if not WEBHOOK_BASE:
        raise RuntimeError("WEBHOOK_BASE is missing")
    return f"{WEBHOOK_BASE.rstrip('/')}{_webhook_path()}"


async def on_startup(bot: Bot):
    await set_bot_commands(bot)
    await bot.set_webhook(
        _webhook_url(),
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=True,
    )


async def on_shutdown(bot: Bot):
    await bot.delete_webhook()


async def health(_: web.Request):
    return web.Response(text="ok")


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    app_context.bot = bot

    init_telethon()
    databases.initialize()

    register_channel(dp)
    register_payments(dp)
    register_private(dp)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    app.router.add_get("/health", health)

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET,
    ).register(app, path=_webhook_path())
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=WEBHOOK_HOST, port=WEBHOOK_PORT)
    await site.start()
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
