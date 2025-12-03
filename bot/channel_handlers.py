import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from data import databases, pay_databases
from . import mapping
from .inviter import ensure_mapping_account_added, send_channel_message_with_deep_link

FREE_TRIAL_QUOTA = 10
BUNDLE_OPTIONS = {
    "20": {"title": "20 subs", "quota": 20, "stars": 100},
    "50": {"title": "50 subs", "quota": 50, "stars": 250},
    "100": {"title": "100 subs", "quota": 100, "stars": 500},
    "500": {"title": "500 subs", "quota": 500, "stars": 2500},
    "1000": {"title": "1000 subs", "quota": 1000, "stars": 5000},
}

logger = logging.getLogger(__name__)

channel_router = Router()
payments_router = Router()


def _bundle_keyboard(channel_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{opt['title']} • {opt['stars']}⭐️",
                    callback_data=f"buy_bundle:{channel_id}:{key}",
                )
            ]
            for key, opt in BUNDLE_OPTIONS.items()
        ]
    )
    return kb


async def _prompt_bundle_purchase(bot: Bot, channel_id: int, admin_user_id: int | None) -> None:
    text = (
        "Choose a bundle to start the campaign.\n"
        f"Includes {FREE_TRIAL_QUOTA} free trial subs;\n"
        "(refund only if zero subs in 30 days.)"
    )
    keyboard = _bundle_keyboard(channel_id)
    if admin_user_id:
        try:
            await bot.send_message(admin_user_id, text, reply_markup=keyboard)
            return
        except TelegramAPIError as exc:
            logger.warning("Could not DM admin %s: %s", admin_user_id, exc)
    await bot.send_message(channel_id, text, reply_markup=keyboard)


@channel_router.my_chat_member()
async def handle_admin_promotion(update: ChatMemberUpdated, bot: Bot) -> None:
    if update.new_chat_member.status != ChatMemberStatus.ADMINISTRATOR:
        return

    channel_id = update.chat.id
    logger.info("Bot added as admin to channel. Channel ID: %s", channel_id)
    try:
        channel = await bot.get_chat(channel_id)
        channel_name = channel.title or ""
    except Exception as exc:
        logger.error("Failed to get channel info for channel %s: %s", channel_id, exc)
        return

    from_user = getattr(update, "from_user", None)
    admin_id = from_user.id if from_user else None
    await asyncio.to_thread(databases.add_channel, channel_id, channel_name, admin_id)
    if admin_id:
        try:
            await asyncio.to_thread(databases.set_channel_admin, channel_id, admin_id)
        except Exception:
            logger.exception("Failed to set admin %s for channel %s", admin_id, channel_id)

    if not await ensure_mapping_account_added(channel_id, bot):
        return

    await asyncio.to_thread(mapping.map_channel_messages, channel_id, bot)
    await send_channel_message_with_deep_link(bot, channel_id)

    active = await asyncio.to_thread(pay_databases.get_active_bundle, channel_id)
    if active:
        return

    await asyncio.to_thread(
        pay_databases.create_bundle,
        channel_id,
        0,
        0,
        FREE_TRIAL_QUOTA,
        datetime.now(timezone.utc) + timedelta(days=30),
        None,
    )
    try:
        await bot.send_message(
            admin_id if admin_id else update.chat.id,
            f"Free trial started: {FREE_TRIAL_QUOTA} subscribers included. "
            "We will notify you to buy a bundle once the trial is used.",
            reply_markup=_bundle_keyboard(update.chat.id),
        )
    except TelegramAPIError as exc:
        logger.warning("Could not send free trial notice for %s: %s", update.chat.id, exc)


@payments_router.callback_query(F.data.startswith("buy_bundle:"))
async def handle_bundle_purchase(call: CallbackQuery, bot: Bot) -> None:
    try:
        member = await bot.get_chat_member(channel_id, call.from_user.id)  # type: ignore[arg-type]
        if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
            await call.answer("Only channel admins can buy.", show_alert=True)
            return
    except TelegramAPIError:
        logger.warning("Could not verify admin status for %s in %s", getattr(call.from_user, "id", None), channel_id)
        await call.answer("Could not verify admin status. Please try again.", show_alert=True)
        return
    if not option:
        await call.answer("Bundle not found.", show_alert=True)
        return

    try:
        member = await bot.get_chat_member(channel_id, call.from_user.id)  # type: ignore[arg-type]
        if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
            await call.answer("Only channel admins can buy.", show_alert=True)
            return
    except TelegramAPIError:
        logger.warning("Could not verify admin status for %s in %s", getattr(call.from_user, "id", None), channel_id)

    payload = f"{channel_id}:{bundle_key}"
    desc = f"{option['quota']} paid subs bundle. Includes {FREE_TRIAL_QUOTA} free trial subs."
    prices = [LabeledPrice(label=f"{option['quota']} subscribers", amount=option["stars"])]
    await bot.send_invoice(
        chat_id=call.from_user.id,  # type: ignore[arg-type]
        title=f"{option['title']} for channel {channel_id}",
        description=desc,
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=prices,
    )
    await call.answer()


@payments_router.pre_checkout_query()
async def checkout(pre_checkout_query: PreCheckoutQuery, bot: Bot) -> None:
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@payments_router.message(F.successful_payment)
async def handle_successful_payment(message: Message, bot: Bot) -> None:
    payload = message.successful_payment.invoice_payload  # type: ignore[union-attr]
    try:
        channel_id_str, bundle_key = payload.split(":")
        channel_id = int(channel_id_str)
        option = BUNDLE_OPTIONS[bundle_key]
    except Exception:
        await message.reply("Payment received but payload is invalid.")
        return

    bundle_id = await asyncio.to_thread(
        pay_databases.create_bundle,
        channel_id,
        option["stars"],
        option["quota"],
        FREE_TRIAL_QUOTA,
        None,
        message.successful_payment.telegram_payment_charge_id,  # type: ignore[union-attr]
    )
    await message.answer(
        f"Bundle activated for channel {channel_id}: {option['quota']} paid subs + "
        f"{FREE_TRIAL_QUOTA} free trial. Bundle ID: {bundle_id}",
    )


@payments_router.chat_member()
async def handle_new_channel_member(update: ChatMemberUpdated, bot: Bot) -> None:
    try:
        channel_id = update.chat.id
        new_member = getattr(update, "new_chat_member", None)
        old_member = getattr(update, "old_chat_member", None)
        user_id = new_member.user.id if new_member else None
        new_status = new_member.status if new_member else None
        old_status = old_member.status if old_member else None
    except Exception:
        return

    if not user_id or new_status != ChatMemberStatus.MEMBER or old_status == ChatMemberStatus.MEMBER:
        return

    active = await asyncio.to_thread(pay_databases.get_active_bundle, channel_id)
    if not active:
        return

    is_new = await asyncio.to_thread(pay_databases.record_subscription, user_id, channel_id, active["id"])
    if not is_new:
        return

    summary = await asyncio.to_thread(pay_databases.bundle_consumption_summary, active["id"])
    if not summary:
        return

    free_exhausted = summary["consumed_free"] >= summary["free_quota"]
    if free_exhausted and summary["purchased_quota"] == 0 and summary["status"] == "active":
        await asyncio.to_thread(pay_databases.mark_bundle_status, active["id"], "expired")
        admin_id = await asyncio.to_thread(databases.get_channel_admin, channel_id)
        await _prompt_bundle_purchase(bot, channel_id, admin_id)


def register(dp: Dispatcher) -> None:
    dp.include_router(channel_router)


def register_payments(dp: Dispatcher) -> None:
    dp.include_router(payments_router)
