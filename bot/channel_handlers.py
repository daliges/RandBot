from telebot import TeleBot
from . import mapping
from .inviter import ensure_mapping_account_added, send_channel_message_with_deep_link

def register(bot: TeleBot) -> None:
    @bot.my_chat_member_handler()
    def handle_admin_promotion(update) -> None:
        if update.new_chat_member.status != "administrator":
            return
        channel_id = update.chat.id
        print(f"Bot added as admin to channel. Channel ID: {channel_id}")

        if not ensure_mapping_account_added(channel_id, bot):
            return

        mapping.map_channel_messages(channel_id, bot)
        send_channel_message_with_deep_link(bot, channel_id)
