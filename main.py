import telebot
from telebot.types import BotCommand, BotCommandScopeDefault, InlineKeyboardMarkup, InlineKeyboardButton
from app_context import bot, channel_media_map, user_channel_map, telethon_client
from dotenv import load_dotenv
import os, re, app_context

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
app_context.bot = telebot.TeleBot(BOT_TOKEN)

# In-memory storage for channel media mappings (use a database for production)
app_context.channel_media_map = {}  # {channel_id: [message_id1, message_id2, ...]}
app_context.user_channel_map = {}  # {user_id: channel_id}

bot = app_context.bot  # For easier access in this file

import mapping, rand

# Set up bot commands for the side menu
def set_bot_commands():
    commands = [
        BotCommand("help", "Help and information about the bot"),
        BotCommand("random", "Get random media from the channel")
    ]
    bot.set_my_commands(commands, scope=BotCommandScopeDefault())

@bot.message_handler(commands=['help'])
def help(message):
    bot.send_message(
        message.chat.id,
        "Hello! I'm your Random bot. Use /random to get random media from the channel in private chat with me."
    )

# Function to send a message with a deep link to the channel
def send_channel_message_with_deep_link(channel_id):
    bot_username = bot.get_me().username
    deep_link_url = f"https://t.me/{bot_username}?start=channel_{channel_id}"

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Interact with the Bot", url=deep_link_url)
    )

    bot.send_message(
        channel_id,
        "Hello! To get random media from the channel, please click the button below to start a private chat.",
        reply_markup=keyboard
    )

# Handler to detect when the bot is added as an admin to a channel
@bot.my_chat_member_handler()
def handle_chat_member_update(chat_member_update):
    new_status = chat_member_update.new_chat_member.status
    if new_status == 'administrator':
        chat_id = chat_member_update.chat.id
        print(f"Bot added as admin to channel. Channel ID: {chat_id}") # add database

        # Map all media messages for the channel
        mapping.map_channel_messages(chat_id, bot)

        send_channel_message_with_deep_link(chat_id)
        # add data to database if needed


set_bot_commands()
bot.polling(none_stop=True)