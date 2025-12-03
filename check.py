import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.exceptions import TelegramAPIError
from dotenv import load_dotenv

import app_context
import databases
import pay_databases
from databases import get_channel_admin, list_pending_intents, mark_intent_status

load_dotenv()

REFUND_METHOD = "refund"
logger = logging.getLogger(__name__)


async def process_expired_bundles(bot: Bot) -> None:
    for bundle in await asyncio.to_thread(pay_databases.find_expired_zero_consumption):
        bundle_id = bundle["id"]
        channel_id = bundle["channel_id"]
        stars = bundle.get("stars_paid", 0)

        try:
            await asyncio.to_thread(
                pay_databases.mark_bundle_status, bundle_id, "refunded" if REFUND_METHOD == "refund" else "credited"
            )
            await asyncio.to_thread(pay_databases.record_refund, bundle_id, stars, REFUND_METHOD)

            admin_id = await asyncio.to_thread(get_channel_admin, channel_id)
            if admin_id:
                try:
                    await bot.send_message(
                        admin_id,
                        f"Bundle {bundle_id} for channel {channel_id} expired with zero usage. "
                        f"{stars}⭐️ has been {'refunded' if REFUND_METHOD == 'refund' else 'credited'}.",
                    )
                except TelegramAPIError:
                    logger.warning("Could not notify admin %s about refund for bundle %s", admin_id, bundle_id)
        except Exception as exc:
            logger.error("Failed to process expired bundle %s: %s", bundle_id, exc)
            continue


async def process_pending_intents(bot: Bot) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    intents = await asyncio.to_thread(list_pending_intents, cutoff)
    for intent in intents:
        try:
            member = await bot.get_chat_member(intent["channel_id"], intent["user_id"])
            status = getattr(member, "status", None)
            subscribed = status in (
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.CREATOR,
                "member",
                "administrator",
                "creator",
                "Member",
                "Administrator",
                "Creator",
            )
        except TelegramAPIError:
            subscribed = False

        await asyncio.to_thread(
            mark_intent_status, intent["id"], "subscribed" if subscribed else "not_subscribed"
        )
        if subscribed:
            await asyncio.to_thread(pay_databases.record_subscription, intent["user_id"], intent["channel_id"], None)


async def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is missing")

    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    app_context.bot = bot

    databases.initialize()
    try:
        await process_pending_intents(bot)
        await process_expired_bundles(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
