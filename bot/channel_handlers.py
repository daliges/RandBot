from telebot import TeleBot, logger, types
from telebot.apihelper import ApiTelegramException
from . import mapping
from .inviter import ensure_mapping_account_added, send_channel_message_with_deep_link
import databases
import pay_databases


FREE_TRIAL_QUOTA = 10
BUNDLE_OPTIONS = {
    "20": {"title": "20 subs", "quota": 20, "stars": 100},
    "50": {"title": "50 subs", "quota": 50, "stars": 250},
    "100": {"title": "100 subs", "quota": 100, "stars": 500},
    "500": {"title": "500 subs", "quota": 500, "stars": 2500},
    "1000": {"title": "1000 subs", "quota": 1000, "stars": 5000},
}


def _bundle_keyboard(channel_id: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    for key, opt in BUNDLE_OPTIONS.items():
        kb.add(
            types.InlineKeyboardButton(
                f"{opt['title']} • {opt['stars']}⭐️",
                callback_data=f"buy_bundle:{channel_id}:{key}",
            )
        )
    return kb


def _prompt_bundle_purchase(bot: TeleBot, channel_id: int, admin_user_id: int | None) -> None:
    text = (
        "Choose a bundle to start the campaign.\n"
        f"Includes {FREE_TRIAL_QUOTA} free trial subs;\n"
        "(refund only if zero subs in 30 days.)"
    )
    keyboard = _bundle_keyboard(channel_id)
    if admin_user_id:
        try:
            bot.send_message(admin_user_id, text, reply_markup=keyboard)
            return
        except ApiTelegramException as exc:
            logger.warning("Could not DM admin %s: %s", admin_user_id, exc)
    bot.send_message(channel_id, text, reply_markup=keyboard)

def register(bot: TeleBot) -> None:
    @bot.my_chat_member_handler()
    def handle_admin_promotion(update) -> None:
        if update.new_chat_member.status != "administrator":
            return
        channel_id = update.chat.id
        logger.info(f"Bot added as admin to channel. Channel ID: {channel_id}")
        try:
            channel_name = bot.get_chat(channel_id).title
        except Exception as e:
            logger.error(f"Failed to get channel info for channel {channel_id}: {e}")
            return

        from_user = getattr(update, "from_user", None)
        admin_id = from_user.id if from_user else None
        databases.add_channel(channel_id, channel_name, admin_id)

        if not ensure_mapping_account_added(channel_id, bot):
            return

        mapping.map_channel_messages(channel_id, bot)
        send_channel_message_with_deep_link(bot, channel_id)

        from_user = getattr(update, "from_user", None)
        admin_id = from_user.id if from_user else None
        _prompt_bundle_purchase(bot, update.chat.id, admin_id)

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("buy_bundle:"))
    def handle_bundle_purchase(call) -> None:
        try:
            _, channel_id_raw, bundle_key = call.data.split(":")
            channel_id = int(channel_id_raw)
        except Exception:
            bot.answer_callback_query(call.id, "Bad bundle data.", show_alert=True)
            return

        option = BUNDLE_OPTIONS.get(bundle_key)
        if not option:
            bot.answer_callback_query(call.id, "Bundle not found.", show_alert=True)
            return

        try:
            member = bot.get_chat_member(channel_id, call.from_user.id)
            if member.status not in ("administrator", "creator"):
                bot.answer_callback_query(call.id, "Only channel admins can buy.", show_alert=True)
                return
        except ApiTelegramException:
            logger.warning("Could not verify admin status for %s in %s", call.from_user.id, channel_id)

        payload = f"{channel_id}:{bundle_key}"
        desc = f"{option['quota']} paid subs bundle. Includes {FREE_TRIAL_QUOTA} free trial subs."
        prices = [types.LabeledPrice(label=f"{option['quota']} subscribers", amount=option["stars"])]
        bot.send_invoice(
            call.from_user.id,
            title=f"{option['title']} for channel {channel_id}",
            description=desc,
            invoice_payload=payload,
            provider_token="",  # Stars payments do not need a provider token
            currency="XTR",
            prices=prices,
        )
        bot.answer_callback_query(call.id)

    @bot.pre_checkout_query_handler(func=lambda q: True)
    def checkout(pre_checkout_query):
        bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

    @bot.message_handler(content_types=["successful_payment"])
    def handle_successful_payment(message):
        payload = message.successful_payment.invoice_payload
        try:
            channel_id_str, bundle_key = payload.split(":")
            channel_id = int(channel_id_str)
            option = BUNDLE_OPTIONS[bundle_key]
        except Exception:
            bot.reply_to(message, "Payment received but payload is invalid.")
            return

        bundle_id = pay_databases.create_bundle(
            channel_id=channel_id,
            stars_paid=option["stars"],
            purchased_quota=option["quota"],
            free_quota=FREE_TRIAL_QUOTA,
            telegram_charge_id=message.successful_payment.telegram_payment_charge_id,
        )
        bot.send_message(
            message.chat.id,
            f"Bundle activated for channel {channel_id}: {option['quota']} paid subs + "
            f"{FREE_TRIAL_QUOTA} free trial. Bundle ID: {bundle_id}",
        )


def register_payments(bot: TeleBot) -> None:
    @bot.my_chat_member_handler()
    def handle_admin_promotion_for_trial(update) -> None:
        if update.new_chat_member.status != "administrator":
            return
        admin_id = getattr(update, "from_user", None).id if getattr(update, "from_user", None) else None
        if admin_id:
            databases.set_channel_admin(update.chat.id, admin_id)

        # Start free trial bundle if none active
        active = pay_databases.get_active_bundle(update.chat.id)
        if active:
            return

        pay_databases.create_bundle(
            channel_id=update.chat.id,
            stars_paid=0,
            purchased_quota=0,
            free_quota=FREE_TRIAL_QUOTA,
            telegram_charge_id=None,
        )
        try:
            bot.send_message(
                admin_id if admin_id else update.chat.id,
                f"Free trial started: {FREE_TRIAL_QUOTA} subscribers included. "
                "We will notify you to buy a bundle once the trial is used.",
                reply_markup=_bundle_keyboard(update.chat.id),
            )
        except ApiTelegramException as exc:
            logger.warning("Could not send free trial notice for %s: %s", update.chat.id, exc)

    @bot.chat_member_handler()
    def handle_new_channel_member(update) -> None:
        try:
            channel_id = update.chat.id
            new_member = getattr(update, "new_chat_member", None)
            old_member = getattr(update, "old_chat_member", None)
            user_id = new_member.user.id if new_member else None
            new_status = new_member.status if new_member else None
            old_status = old_member.status if old_member else None
        except Exception:
            return

        if not user_id or new_status != "member" or old_status == "member":
            return

        active = pay_databases.get_active_bundle(channel_id)
        if not active:
            return

        is_new = pay_databases.record_subscription(user_id, channel_id, active["id"])
        if not is_new:
            return

        summary = pay_databases.bundle_consumption_summary(active["id"])
        if not summary:
            return

        free_exhausted = summary["consumed_free"] >= summary["free_quota"]
        if free_exhausted and summary["purchased_quota"] == 0 and summary["status"] == "active":
            pay_databases.mark_bundle_status(active["id"], "expired")
            admin_id = databases.get_channel_admin(channel_id)
            _prompt_bundle_purchase(bot, channel_id, admin_id)
