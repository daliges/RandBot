import os
from dotenv import load_dotenv
import telebot

import app_context
from telethon_runner import init_telethon
from bot.channel_handlers import register as register_channel
from bot.private_handlers import register as register_private
from bot.private_handlers import set_bot_commands

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

app_context.bot = telebot.TeleBot(BOT_TOKEN)
init_telethon()

app_context.channel_media_map = {}
app_context.user_channel_map = {}

bot = app_context.bot
set_bot_commands(bot)
register_channel(bot)
register_private(bot)

bot.polling(none_stop=True)
