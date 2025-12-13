import asyncio
import json
import logging
import os
import random

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand,
    BotCommandScopeDefault,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    BotCommandScopeAllPrivateChats,
)

from data import databases, pay_databases
from bot.channel_watchers import MEDIA_CACHE_KEY, _persist_map
from data.databases import redis_client
from .utils import prompt_bundle_purchase, subscribe_keyboard, channel_link_and_name

CHANNEL_IDS_CACHE_KEY = os.getenv("CHANNEL_IDS_CACHE_KEY", "channel_ids_cache")
CHANNEL_IDS_TTL = int(os.getenv("CHANNEL_IDS_TTL", "300"))

router = Router()
logger = logging.getLogger(__name__)


async def set_bot_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="help", description="Help and info about the bot"),
        BotCommand(command="random", description="Get random media from the channel"),
        BotCommand(command="admin", description="Admin help info"),
    ]
    for scope in (BotCommandScopeDefault(), BotCommandScopeAllPrivateChats()):
        await bot.delete_my_commands(scope=scope)
        await bot.set_my_commands(commands, scope=scope)


async def _load_media_map(channel_id: int) -> list[int]:
    cached = redis_client.hget(MEDIA_CACHE_KEY, str(channel_id))
    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            redis_client.hdel(MEDIA_CACHE_KEY, str(channel_id))

    media_map = await asyncio.to_thread(databases.get_channel_media_map, channel_id)
    if media_map is None:
        media_map = []
    if media_map:
        redis_client.hset(MEDIA_CACHE_KEY, str(channel_id), json.dumps(media_map))
    return media_map


async def _get_channel_ids() -> list[int]:
    cached = redis_client.get(CHANNEL_IDS_CACHE_KEY)
    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            redis_client.delete(CHANNEL_IDS_CACHE_KEY)

    try:
        ids = await asyncio.to_thread(pay_databases.list_active_channel_ids)
    except Exception:
        logger.exception("Failed to list active mapped channels")
        return []

    if ids:
        redis_client.setex(CHANNEL_IDS_CACHE_KEY, CHANNEL_IDS_TTL, json.dumps(ids))
    return ids


async def _refresh_channel_ids_cache() -> list[int]:
    redis_client.delete(CHANNEL_IDS_CACHE_KEY)
    return await _get_channel_ids()


@router.message(Command("help"))
async def help_cmd(message: Message) -> None:
    await message.answer(
        "This bot sends random media from linked channels.\n"
        "Use /random to get item.\n"
        "Admins: use /admin for admin commands and tips."
    )


@router.message(Command("admin"))
async def admin_help(message: Message) -> None:
    await message.answer(
        "Purpose: \nShares random media from linked channels " \
        "so users can pull a surprise item on demand. "
        "It's made to help channels promote their content and give users an easier way to find channels.\n\n" \
        "How it works: \nYou add bot as admin to your channel; bot scans and adds all content to common feed; "
        "then /random returns a random channel and post from it.\n" \
        "If you don't get it, think of it as TikTok feed but for Telegram channels.\n\n"
        "Payments & traffic: \nAdding the bot gives trial with 10 free subscribers; " \
        "your channel stays in /random while any trial/bundle is active.\n"
        "Quota is spent when people subscribe; only the first join per user counts and "
        "if person stays for certain time in channel. " \
        "We spend free quota first, then paid.\n"
        "If free quota is used and there's no paid bundle, " \
        "traffic pauses and we'll prompt you to buy.\n"
        "If no users subscribe within a month, stars are auto-refunded/credited.\n" \
        "Use /bundles to see purchase options."
    )


@router.message(Command("bundles"))
async def bundles_info(message: Message) -> None:
    admin_id = getattr(message.from_user, "id", None)
    channels = await asyncio.to_thread(databases.list_admin_channel_ids, admin_id)
    if not channels:
        await message.answer("I don't see any channels you admin that are linked to the bot.")
        return
    channel_id = channels[0]  # or prompt to choose if multiple
    await prompt_bundle_purchase(message.bot, channel_id, admin_id)


@router.message(CommandStart())
async def start(message: Message, bot: Bot) -> None:
    text = message.text or ""
    if text.startswith("/start channel_"):
        try:
            raw_channel_id = text[len("/start channel_") :]
            normalized_channel_id = (
                raw_channel_id.replace("_", "-", 1) if raw_channel_id.startswith("_") else raw_channel_id
            )
            if not normalized_channel_id.lstrip("-").isdigit():
                await message.answer("Invalid channel ID in deep link.")
                return
            channel_id = int(normalized_channel_id)
            await asyncio.to_thread(databases.link_user_to_channel, message.from_user.id, channel_id)  # type: ignore[arg-type]
        except (IndexError, ValueError) as exc:
            logger.warning("Error parsing deep link: %s", exc)
            await message.answer("Invalid deep link format.")
            return

        await message.answer(
            "Hello! The channel is connected to the bot now. "
            "Use /random to get random media from linked channels."
        )
    else:
        await message.answer("Hello! I'm your Random bot. Use /random to get random media.")

    await _refresh_channel_ids_cache()


async def _fetch_random_media(message: Message, bot: Bot) -> None:
    channel_ids = await _get_channel_ids()
    if not channel_ids:
        await message.answer("No channels are mapped yet.")
        return
    channel_id = random.choice(channel_ids)

    media_map = await _load_media_map(channel_id)
    attempts = min(len(media_map), 10)
    while media_map and attempts:
        random_media_id = random.choice(media_map)
        try:
            name, link = await channel_link_and_name(bot, channel_id)
            if not link:
                await message.answer(f"Can't open {name} right now.")
                return

            await bot.copy_message(
                chat_id=message.chat.id,
                from_chat_id=channel_id,
                message_id=random_media_id,
                reply_markup=subscribe_keyboard(channel_id),
            )
            return
        except TelegramBadRequest as exc:
            text = str(exc).lower()
            if "message to forward not found" in text or "message_id_invalid" in text or "message id invalid" in text:
                media_map = [mid for mid in media_map if mid != random_media_id]
                await asyncio.to_thread(_persist_map, channel_id, media_map)
                attempts -= 1
                continue
            logger.exception("Telegram API error for channel %s", channel_id)
            break
        except TelegramAPIError:
            logger.exception("Error forwarding media from channel %s", channel_id)
            break

    await message.answer("Failed to fetch media. Please try again later.")


@router.message(Command("random"))
async def fetch_random_media(message: Message, bot: Bot) -> None:
    await _fetch_random_media(message, bot)


@router.callback_query(F.data == "Next")
async def handle_next_media(call: CallbackQuery, bot: Bot) -> None:
    if call.message:
        await _fetch_random_media(call.message, bot)
    await call.answer()


@router.callback_query(F.data.startswith("subscribe:"))
async def handle_subscribe(call: CallbackQuery, bot: Bot) -> None:
    try:
        _, raw_channel_id = call.data.split(":", 1)  # type: ignore[union-attr]
        channel_id = int(raw_channel_id)
    except (ValueError, AttributeError):
        await call.answer("Invalid subscribe data.", show_alert=True)
        return

    name, link = await channel_link_and_name(bot, channel_id)
    if not link or not str(link).startswith("http"):
        await call.answer("Can't open the channel right now.", show_alert=True)
        return

    try:
        await asyncio.to_thread(databases.save_subscription_intent, call.from_user.id, channel_id)  # type: ignore[arg-type]
    except Exception:
        logger.exception("Failed to save intent for user %s channel %s", getattr(call.from_user, "id", None), channel_id)

    url_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Open {name}", url=link)],
            [InlineKeyboardButton(text="Next", callback_data="Next")],
        ]
    )

    try:
        member = await bot.get_chat_member(channel_id, call.from_user.id)  # type: ignore[arg-type]
        already_in = getattr(member, "status", None) in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
        )
    except TelegramAPIError:
        already_in = False

    if already_in:
        await call.answer("You’re already subscribed ✅", show_alert=True)
        return

    await call.answer()
    try:
        if call.message:
            await bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=url_kb,
            )
        else:
            await bot.send_message(call.from_user.id, f"Open {name}", reply_markup=url_kb)  # type: ignore[arg-type]
    except TelegramAPIError:
        if call.message:
            await bot.send_message(call.message.chat.id, f"Open {name}", reply_markup=url_kb)


def register(dp: Dispatcher) -> None:
    """Attach private-chat handlers to the dispatcher."""
    dp.include_router(router)
