import os
from dotenv import load_dotenv
import telebot
import sqlite3
import json

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

connection1 = sqlite3.connect('channels.sql')
cur1 = connection1.cursor()

cur1.execute('CREATE TABLE IF NOT EXISTS channels (channel_id int auto_increment primary key,' \
            ' channel_name varchar(50))')
connection1.commit()

connection2 = sqlite3.connect('mappings.sql')
cur2 = connection2.cursor()

json.dumps(app_context.channel_media_map) # serialization because sqlite doesn't support dicts natively

cur2.execute('CREATE TABLE IF NOT EXISTS mappings (channel_id int primary key,' \
            ' channel_media_map text)')
connection2.commit()

cur1.close()
cur2.close()
connection1.close()
connection2.close()

bot = app_context.bot
set_bot_commands(bot)
register_channel(bot)
register_private(bot)

bot.polling(none_stop=True)
