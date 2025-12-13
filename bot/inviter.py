import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from telethon import errors as telethon_errors, functions

import app_context

logger = logging.getLogger(__name__)


async def send_channel_message_with_deep_link(bot: Bot, channel_id: int) -> None:
    try:
        me = await bot.get_me()
        bot_username = me.username
    except TelegramAPIError as exc:
        logger.warning("Failed to fetch bot info for deep link: %s", exc)
        return

    deep_link_url = f"https://t.me/{bot_username}?start=channel_{channel_id}"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Interact with the Bot", url=deep_link_url)]]
    )

    try:
        await bot.send_message(
            channel_id,
            "Hello! To get random media from the channel, please click the button below to start a private chat.",
            reply_markup=keyboard,
        )
    except TelegramAPIError as exc:
        logger.warning("Failed to send deep link to channel %s: %s", channel_id, exc)


async def ensure_mapping_account_added(channel_id: int, bot: Bot) -> bool:
    loop = app_context.telethon_loop
    client = app_context.telethon_client
    if not loop or not client:
        logger.info("Telethon client is not ready; helper account cannot be invited.")
        return False

    async def _already_present() -> bool:
        try:
            await client.get_entity(channel_id)
            return True
        except (ValueError, telethon_errors.rpcerrorlist.ChannelPrivateError):
            return False

    already_present = await asyncio.to_thread(
        lambda: asyncio.run_coroutine_threadsafe(_already_present(), loop).result()
    )
    if already_present:
        return True

    try:
        invite = await bot.create_chat_invite_link(
            channel_id,
            name="RandBot helper access",
            creates_join_request=False,
        )
    except TelegramAPIError as api_exc:
        logger.warning("Failed to create invite link for %s: %s", channel_id, api_exc)
        await bot.send_message(
            channel_id,
            "I need the 'Add Users' permission to invite my helper account.\n"
            "Please grant that permission and try again.",
        )
        return False

    invite_hash = _extract_invite_hash(invite.invite_link)

    async def _join_via_invite() -> bool:
        try:
            await client(functions.messages.ImportChatInviteRequest(invite_hash))
            logger.info("Helper account joined channel %s.", channel_id)
            return True
        except telethon_errors.UserAlreadyParticipantError:
            return True
        except telethon_errors.InviteRequestSentError:
            logger.info("Join request sent; waiting for approval.")
            return False
        except telethon_errors.rpcerrorlist.ChatAdminRequiredError as exc:
            logger.warning("Channel denied helper join: %s", exc)
            return False
        except telethon_errors.rpcbase.TelegramError as exc:
            logger.warning("Join failed for %s: %s", channel_id, exc)
            return False

    return await asyncio.to_thread(
        lambda: asyncio.run_coroutine_threadsafe(_join_via_invite(), loop).result()
    )


def _extract_invite_hash(invite_link: str) -> str:
    if "+" in invite_link:
        return invite_link.split("+", 1)[1]
    if "joinchat/" in invite_link:
        return invite_link.rsplit("/", 1)[1]
    raise ValueError(f"Unsupported invite link format: {invite_link}")
