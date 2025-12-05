import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


FREE_TRIAL_QUOTA = 10
BUNDLE_OPTIONS = {
    "20": {"title": "20 subs", "quota": 20, "stars": 100},
    "50": {"title": "50 subs", "quota": 50, "stars": 250},
    "100": {"title": "100 subs", "quota": 100, "stars": 500},
    "500": {"title": "500 subs", "quota": 500, "stars": 2500},
    "1000": {"title": "1000 subs", "quota": 1000, "stars": 5000},
}


logger = logging.getLogger(__name__)


def subscribe_keyboard(channel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Subscribe", callback_data=f"subscribe:{channel_id}")],
            [InlineKeyboardButton(text="Next", callback_data="Next")],
        ]
    )


def bundle_keyboard(channel_id: int) -> InlineKeyboardMarkup:
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


async def get_channel_name(bot: Bot, channel_id: int) -> str:
    try:
        chat = await bot.get_chat(channel_id)
        return chat.title or "Unknown Channel"
    except Exception as exc:
        logger.warning("Error fetching channel name for ID %s: %s", channel_id, exc)
        return "Unknown Channel"


async def prompt_bundle_purchase(bot: Bot, channel_id: int, admin_user_id: int | None) -> None:
    text = (
        "Choose a bundle to start the campaign.\n"
        f"Includes {FREE_TRIAL_QUOTA} free trial subs;\n"
        "(refund only if zero subs in 30 days.)"
    )
    keyboard = bundle_keyboard(channel_id)
    if admin_user_id:
        try:
            await bot.send_message(admin_user_id, text, reply_markup=keyboard)
            return
        except TelegramAPIError as exc:
            logger.warning("Could not DM admin %s: %s", admin_user_id, exc)
    await bot.send_message(channel_id, text, reply_markup=keyboard)


async def channel_link_and_name(bot: Bot, channel_id: int) -> tuple[str, str | None]:
    chat = await bot.get_chat(channel_id)
    name = chat.title or "Channel"
    link = f"https://t.me/{chat.username}" if getattr(chat, "username", None) else None
    if not link:
        try:
            invite = await bot.create_chat_invite_link(
                channel_id, name="RandBot subscribe", creates_join_request=False
            )
            link = invite.invite_link
        except TelegramAPIError as exc:
            logger.warning("Could not create invite for %s: %s", channel_id, exc)
            return name, None
    return name, link
