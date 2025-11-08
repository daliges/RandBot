import os
from dotenv import load_dotenv
import telebot
import sqlite3
import json

import app_context
import databases
from telethon_runner import init_telethon
from bot.channel_handlers import register as register_channel
from bot.private_handlers import register as register_private
from bot.private_handlers import set_bot_commands

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

app_context.bot = telebot.TeleBot(BOT_TOKEN)
init_telethon()

databases.initialize()

try:
    app_context.channel_media_map = databases.load_channel_media_map()
except Exception as e:
    print(f"Error loading channel media map from database or a map is empty: {e}")
    app_context.channel_media_map = {}
app_context.user_channel_map = {}

bot = app_context.bot
set_bot_commands(bot)
register_channel(bot)
register_private(bot)

bot.polling(none_stop=True)
