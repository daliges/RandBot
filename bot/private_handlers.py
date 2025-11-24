import json
from telebot import TeleBot, logger, types
from telebot.types import BotCommand, BotCommandScopeDefault
from telebot.apihelper import ApiTelegramException
import random, databases
from databases import redis_client
from bot.channel_watchers import _persist_map, MEDIA_CACHE_KEY

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

    # Command to fetch random media
    @bot.message_handler(commands=['random'])
    def fetch_random_media(message):
        user_id = message.from_user.id

        try:
            channel_ids = databases.get_mapped_channel_ids()
        except Exception:
            logger.exception("Failed to list mapped channels")
            bot.send_message(message.chat.id, "Could not load channels, try again later.")
            return

        if not channel_ids:
            bot.send_message(message.chat.id, "No channels are mapped yet.")
            return

        random.shuffle(channel_ids)  # randomize channel choice

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("Next"))

        for channel_id in channel_ids:
            media_map = _load_media_map(channel_id)
            attempts = min(len(media_map), 10)
            while media_map and attempts:
                random_media_id = random.choice(media_map)
                try:
                    bot.forward_message(message.chat.id, channel_id, random_media_id)
                    bot.send_message(message.chat.id, "Click 'Next' to get another one.", reply_markup=markup)
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

    
