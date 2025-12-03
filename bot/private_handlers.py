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
)

from data import databases, pay_databases
from bot.channel_watchers import MEDIA_CACHE_KEY, _persist_map
from data.databases import redis_client

CHANNEL_IDS_CACHE_KEY = os.getenv("CHANNEL_IDS_CACHE_KEY", "channel_ids_cache")
CHANNEL_IDS_TTL = int(os.getenv("CHANNEL_IDS_TTL", "300"))

router = Router()
logger = logging.getLogger(__name__)


async def set_bot_commands(bot: Bot) -> None:
    await bot.delete_my_commands(scope=BotCommandScopeDefault())
    commands = [
        BotCommand(command="help", description="Help and info about the bot"),
        BotCommand(command="random", description="Get random media from the channel"),
        BotCommand(command="admin", description="Admin help info"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())


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


def _subscribe_keyboard(channel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Subscribe", callback_data=f"subscribe:{channel_id}")],
            [InlineKeyboardButton(text="Next", callback_data="Next")],
        ]
    )


async def _channel_link_and_name(bot: Bot, channel_id: int) -> tuple[str, str | None]:
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


async def _get_channel_name(bot: Bot, channel_id: int) -> str:
    try:
        chat = await bot.get_chat(channel_id)
        return chat.title or "Unknown Channel"
    except Exception as exc:
        logger.warning("Error fetching channel name for ID %s: %s", channel_id, exc)
        return "Unknown Channel"


@router.message(Command("help"))
async def help_cmd(message: Message) -> None:
    await message.answer(
        "This bot allows you to get random media from the channel you link via deep link. "
        "\nUse command /random to get random media from the channel "
        "\nIf you are an admin, use /admin for admin help."
    )


@router.message(Command("admin"))
async def admin_help(message: Message) -> None:
    await message.answer(
        "Admin Help:\n"
        "Add the bot as an admin to your channel with permission to post messages "
        "and add subscribers.\n"
        "Don't worry the bot will add only one subscriber (itself) to your channel.\n"
        "It's made to ensure the bot can function properly."
    )


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

        channel_name = await _get_channel_name(bot, channel_id)  # type: ignore[arg-type]
        await message.answer(
            f"Hello! You are now connected to the channel : {channel_name}. "
            "Use /random to get random media from the channel."
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
            name, link = await _channel_link_and_name(bot, channel_id)
            if not link:
                await message.answer(f"Can't open {name} right now.")
                return

            await bot.copy_message(
                chat_id=message.chat.id,
                from_chat_id=channel_id,
                message_id=random_media_id,
                reply_markup=_subscribe_keyboard(channel_id),
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

    name, link = await _channel_link_and_name(bot, channel_id)
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
