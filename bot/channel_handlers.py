from telebot import TeleBot
from . import mapping
from .inviter import ensure_mapping_account_added, send_channel_message_with_deep_link
import sqlite3

def register(bot: TeleBot) -> None:
    @bot.my_chat_member_handler()
    def handle_admin_promotion(update) -> None:
        if update.new_chat_member.status != "administrator":
            return
        channel_id = update.chat.id
        print(f"Bot added as admin to channel. Channel ID: {channel_id}")
        channel_name = bot.get_chat(channel_id).title

        conn = sqlite3.connect('channels.sql')
        cur = conn.cursor()
        cur.execute('INSERT OR IGNORE INTO channels (channel_id, channel_name) VALUES (?, ?)',
    (channel_id, channel_name))
        conn.commit()
        cur.close()
        conn.close()

        if not ensure_mapping_account_added(channel_id, bot):
            return

        mapping.map_channel_messages(channel_id, bot)
        send_channel_message_with_deep_link(bot, channel_id)
