import os
from dotenv import load_dotenv
import telebot
import app_context
import databases
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from telethon_runner import init_telethon
from bot.channel_handlers import register as register_channel
from bot.private_handlers import register as register_private
from bot.private_handlers import set_bot_commands

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

session = requests.Session()
retry = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=(500, 502, 503, 504),
    allowed_methods=("GET", "POST"),
)
adapter = HTTPAdapter(max_retries=retry)
session.mount("https://", adapter)
telebot.apihelper.session = session

app_context.bot = telebot.TeleBot(BOT_TOKEN)
init_telethon()

databases.initialize()

bot = app_context.bot
set_bot_commands(bot)
register_channel(bot)
register_private(bot)

bot.polling(none_stop=True)
