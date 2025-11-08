from telebot import TeleBot
from . import mapping
from .inviter import ensure_mapping_account_added, send_channel_message_with_deep_link
import sqlite3
import databases

def register(bot: TeleBot) -> None:
    @bot.my_chat_member_handler()
    def handle_admin_promotion(update) -> None:
        if update.new_chat_member.status != "administrator":
            return
        channel_id = update.chat.id
        print(f"Bot added as admin to channel. Channel ID: {channel_id}")
        try:
            channel_name = bot.get_chat(channel_id).title
        except Exception as e:
            print(f"Failed to get channel info: {e}")
            return

        databases.add_channel(channel_id, channel_name)

        if not ensure_mapping_account_added(channel_id, bot):
            return

        mapping.map_channel_messages(channel_id, bot)
        send_channel_message_with_deep_link(bot, channel_id)
