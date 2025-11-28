import json
import os
from telebot import TeleBot, logger, types
from telebot.types import BotCommand, BotCommandScopeDefault
from telebot.apihelper import ApiTelegramException
import random, databases
from databases import redis_client
from bot.channel_watchers import _persist_map, MEDIA_CACHE_KEY

CHANNEL_IDS_CACHE_KEY = os.getenv("CHANNEL_IDS_CACHE_KEY")
CHANNEL_IDS_TTL = int(os.getenv("CHANNEL_IDS_TTL"))

# # Set up bot commands for the side menu
def set_bot_commands(bot: TeleBot) -> None:
    bot.delete_my_commands(scope=BotCommandScopeDefault())
    commands = [
        BotCommand("help", "Help and info about the bot"),
        BotCommand("random", "Get random media from the channel"),
        BotCommand("admin", "Admin help info")
    ]
    bot.set_my_commands(commands, scope=BotCommandScopeDefault())


def _load_media_map(channel_id: int) -> list[int]:
    cached = redis_client.hget(MEDIA_CACHE_KEY, str(channel_id))
    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            redis_client.hdel(MEDIA_CACHE_KEY, str(channel_id))
    media_map = databases.get_channel_media_map(channel_id)
    if media_map is None:
        media_map = []
    if media_map:
        redis_client.hset(MEDIA_CACHE_KEY, str(channel_id), json.dumps(media_map))
    return media_map


def _get_channel_ids() -> list[int]:
    # try Redis first
    cached = redis_client.get(CHANNEL_IDS_CACHE_KEY)
    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            redis_client.delete(CHANNEL_IDS_CACHE_KEY)

    # fallback to DB
    try:
        ids = databases.get_mapped_channel_ids()
    except Exception:
        logger.exception("Failed to list mapped channels")
        return []

    if ids:
        redis_client.setex(CHANNEL_IDS_CACHE_KEY, CHANNEL_IDS_TTL, json.dumps(ids))
    return ids


def _refresh_channel_ids_cache() -> list[int]:
    redis_client.delete(CHANNEL_IDS_CACHE_KEY)
    ids = _get_channel_ids()
    return ids


def _subscribe_keyboard(channel_id: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Subscribe", callback_data=f"subscribe:{channel_id}"))
    return kb


def _channel_link_and_name(bot: TeleBot, channel_id: int) -> tuple[str, str | None]:
    chat = bot.get_chat(channel_id)
    name = chat.title or "Channel"
    link = f"https://t.me/{chat.username}" if getattr(chat, "username", None) else None
    if not link:
        try:
            invite = bot.create_chat_invite_link(
                channel_id, name="RandBot subscribe", creates_join_request=False
            )
            link = invite.invite_link
        except ApiTelegramException as exc:
            logger.warning("Could not create invite for %s: %s", channel_id, exc)
            return name, None
    return name, link



def register(bot: TeleBot) -> None:
    @bot.message_handler(commands=['help'])
    def help(message):
        bot.send_message(
            message.chat.id,
            "This bot allows you to get random media from the channel you link via deep link. " \
            "\nUse command /random to get random media from the channel " \
            "\nIf you are an admin, use /admin for admin help."
        )

    @bot.message_handler(commands=['admin'])
    def admin_help(message):
        bot.send_message(
            message.chat.id,
            "Admin Help:\n" \
            "Add the bot as an admin to your channel with permission to post messages " \
            "and add subscribers.\n" \
            "Don't worry the bot will add only one subscriber (itself) to your channel.\n" \
            "It's made to ensure the bot can function properly." \
        )

    # Function to get the channel name based on the channel_id
    def get_channel_name(channel_id):
        try:
            chat = bot.get_chat(channel_id)  # Fetch chat details using the channel_id
            return chat.title  # Return the channel's title (name)
        except Exception as e:
            print(f"Error fetching channel name for ID {channel_id}: {e}")
            return "Unknown Channel"  # Fallback if the channel name cannot be retrieved


    # Handle the deep link in private chat
    @bot.message_handler(commands=['start'])
    def start(message):
        # Check if the user started the bot with a deep link
        if message.text.startswith('/start channel_'):
            try:
                # Extract everything after 'channel_'
                raw_channel_id = message.text[len('/start channel_'):]
                # Convert back underscores to minus for negative channel IDs if needed
                normalized_channel_id = raw_channel_id.replace('_', '-', 1) if raw_channel_id.startswith('_') else raw_channel_id
                channel_id = int(normalized_channel_id) if normalized_channel_id.lstrip('-').isdigit() else normalized_channel_id

                databases.link_user_to_channel(message.from_user.id, channel_id)
            except (IndexError, ValueError) as e:
                print(f"Error parsing deep link: {e}")
                bot.send_message(message.chat.id, "Invalid deep link format.")
                return

            channel_name = get_channel_name(channel_id)
            bot.send_message(
                message.chat.id,
                f"Hello! You are now connected to the channel : {channel_name}. "
                "Use /random to get random media from the channel."
            )
        else:
            bot.send_message(
                message.chat.id,
                "Hello! I'm your Random bot. Use /random to get random media."
            )

        _refresh_channel_ids_cache()

    # Command to fetch random media
    @bot.message_handler(commands=['random'])
    def fetch_random_media(message):
        user_id = message.from_user.id

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("Next"))

        channel_ids = _get_channel_ids()
        if not channel_ids:
            bot.send_message(message.chat.id, "No channels are mapped yet.")
            return
        channel_id = random.choice(channel_ids)

        chat = bot.get_chat(channel_id)
        channel_name = chat.title or "Channel"
        channel_link = f"https://t.me/{chat.username}" if getattr(chat, "username", None) else None

        media_map = _load_media_map(channel_id)
        attempts = min(len(media_map), 10)
        while media_map and attempts:
            random_media_id = random.choice(media_map)
            try:
                channel_name, channel_link = _channel_link_and_name(bot, channel_id)
                if not channel_link:
                    bot.send_message(message.chat.id, f"Can't open {channel_name} right now.")
                    return

                bot.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=channel_id,
                    message_id=random_media_id,
                    reply_markup=_subscribe_keyboard(channel_id),
                )
                return
            except ApiTelegramException as exc:
                text = getattr(getattr(exc, "result", None), "text", "").lower()
                if "message to forward not found" in text or "message_id_invalid" in text or "message id invalid" in text:
                    media_map = [mid for mid in media_map if mid != random_media_id]
                    _persist_map(channel_id, media_map)
                    attempts -= 1
                    continue
                logger.exception("Telegram API error for channel %s", channel_id)
                break
            except Exception:
                logger.exception("Error forwarding media from channel %s", channel_id)
                break

        bot.send_message(
            message.chat.id,
            "Failed to fetch media. Please try again later.",
        )

    @bot.message_handler(func=lambda msg: msg.text == "Next")
    def next_random_media(message):
        fetch_random_media(message)

    
    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("subscribe:"))
    def handle_subscribe(call):
        try:
            _, raw_channel_id = call.data.split(":", 1)
            channel_id = int(raw_channel_id)
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "Invalid subscribe data.", show_alert=True)
            return

        name, link = _channel_link_and_name(bot, channel_id)
        if not link or not str(link).startswith("http"):
            bot.answer_callback_query(call.id, "Can't open the channel right now.", show_alert=True)
            return

        try:
            databases.save_subscription_intent(call.from_user.id, channel_id)
        except Exception:
            logger.exception("Failed to save intent for user %s channel %s", call.from_user.id, channel_id)

        url_kb = types.InlineKeyboardMarkup()
        url_kb.add(types.InlineKeyboardButton(f"Open {name}", url=link))

        bot.answer_callback_query(call.id)  # ack the tap; avoid URL in callback to prevent URL_INVALID
        try:
            bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=url_kb,
            )
        except ApiTelegramException:
            bot.send_message(call.message.chat.id, f"Open {name}", reply_markup=url_kb)



  
