from datetime import datetime, timedelta, timezone
from enum import member
from telebot.apihelper import ApiTelegramException
from app_context import bot
import pay_databases
from databases import list_pending_intents, mark_intent_status


def main():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    for intent in list_pending_intents(cutoff):
        try:
            member = bot.get_chat_member(intent["channel_id"], intent["user_id"])
            subscribed = getattr(member, "status", None) in ("member", "administrator", "creator")
        except ApiTelegramException:
            subscribed = False

        mark_intent_status(intent["id"], "subscribed" if subscribed else "not_subscribed")
        if subscribed:
            pay_databases.record_subscription(intent["user_id"], intent["channel_id"], None)


if __name__ == "__main__":
    main()
