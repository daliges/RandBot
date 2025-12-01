from datetime import datetime, timedelta, timezone
from enum import member
from telebot.apihelper import ApiTelegramException, logger
from app_context import bot
import pay_databases
from databases import get_channel_admin, list_pending_intents, mark_intent_status


REFUND_METHOD = "refund"


def process_expired_bundles():
    for bundle in pay_databases.find_expired_zero_consumption():
        bundle_id = bundle["id"]
        channel_id = bundle["channel_id"]
        stars = bundle.get("stars_paid", 0)

        try:
            # mark and record refund/credit
            pay_databases.mark_bundle_status(bundle_id, "refunded" if REFUND_METHOD == "refund" else "credited")
            pay_databases.record_refund(bundle_id, stars_refunded=stars, method=REFUND_METHOD)

            admin_id = get_channel_admin(channel_id)
            if admin_id:
                try:
                    bot.send_message(
                        admin_id,
                        f"Bundle {bundle_id} for channel {channel_id} expired with zero usage. "
                        f"{stars}⭐️ has been {'refunded' if REFUND_METHOD == 'refund' else 'credited'}."
                    )
                except ApiTelegramException:
                    logger.warning("Could not notify admin %s about refund for bundle %s", admin_id, bundle_id)
        except Exception as e:
            logger.error("Failed to process expired bundle %s: %s", bundle_id, e)
            continue


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

    process_expired_bundles()


if __name__ == "__main__":
    main()
