import json
from telebot import TeleBot, logger, types
from telebot.types import BotCommand, BotCommandScopeDefault
from bot import mapping
from bot.join_helpers import _extract_channel_link, _join_channel
import random, databases
from databases import redis_client
from telethon.errors import ChannelPrivateError, FloodWaitError, InviteHashInvalidError, InviteHashExpiredError

# Set up bot commands for the side menu
def set_bot_commands(bot: TeleBot) -> None:
    commands = [
        BotCommand("help", "Help and information about the bot"),
        BotCommand("random", "Get random media from the channel"),
        BotCommand("link", "Link your channel to the bot"),
        BotCommand("admin", "Admin help info")
    ]
    bot.set_my_commands(commands, scope=BotCommandScopeDefault())

def register(bot: TeleBot) -> None:
    @bot.message_handler(commands=['help'])
    def help(message):
        bot.send_message(
            message.chat.id,
            "This bot allows you to get random media from a linked channel. " \
            "Use /link to link your channel and /random to get random media." \
            "You can also use the deep link sent to your channel to link it."
        )


    @bot.message_handler(commands=['admin'])
    def admin_help(message):
        bot.send_message(
            message.chat.id,
            "If you are admin of a channel, add the bot as an admin to the channel " \
            "grant it permission to post messages and add subscribers. " \
            "" \
            "Don't worry, the bot will add only one subscriber account " \
            "for proper functionality. "
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
                "Hello! I'm your Random bot. " \
                "" \
                "Use /help to see help information. " \
                "" \
                "You can link any channel by using command /link " \
                "or use the deep link sent to your channel. "
            )

    # Command to fetch random media
    @bot.message_handler(commands=['random'])
    def fetch_random_media(message):
        user_id = message.from_user.id

        try:
            user_channel_id = databases.get_user_channel(user_id)
        except Exception as exc:  
            logger.exception("Failed to read channel for user %s", user_id)
            bot.send_message(message.chat.id,
                    "Could not verify your channel link. Please try again later.")
            return

        if user_channel_id is None:
            logger.info("User %s requested /random without a linked channel", user_id)
            bot.send_message(
                message.chat.id,
                "You are not connected to any channel. Use the channel deep link first.",
            )
            return

        channel_id = user_channel_id

        # Check if the channel is mapped
        media_map: list[int] = []
        try:
            if not redis_client.hget("channel_media_map", str(channel_id)):

                if not databases.is_channel_in_mappings(channel_id):
                    bot.send_message(
                        message.chat.id,
                        "The channel is not mapped yet. " \
                        "Please ensure the bot is added as an admin to the channel."
                    )
                    return
                else:
                    media_map = databases.get_channel_media_map(channel_id)
                    redis_client.hset("channel_media_map", str(channel_id), json.dumps(media_map))
                    redis_client.expire(f"channel_media_map:{channel_id}", 3600)

            else:
                loaded_data = json.loads(redis_client.hget("channel_media_map", str(channel_id)))
                if not isinstance(loaded_data, list):
                    raise ValueError(f"Invalid media_map format in Redis for channel {channel_id}")
                media_map = loaded_data

            if not media_map:
                bot.send_message(
                    message.chat.id,
                    "No media available in this channel yet. Please ensure the channel has media."
                )
                return

        except redis_client.RedisError as exc:
            logger.exception("Redis error while fetching media map for channel %s", channel_id)
            # Optionally: fallback to database-only read
        except databases.DatabaseError as exc:
            logger.exception("Database error while fetching media map for channel %s", channel_id)
        except Exception as exc:
            logger.exception("Unexpected error while fetching media map for channel %s", channel_id)

            bot.send_message(
                message.chat.id,
                "Could not fetch media from the channel. Please try again later."
            )
            return

        random_media_id = random.choice(media_map)
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("Next"))

        # Forward the media to the user
        try:
            bot.forward_message(message.chat.id, channel_id, random_media_id)
            bot.send_message(
                message.chat.id,
                "Click 'Next' to get another one.",
                reply_markup=markup
            )
        except Exception as e:
            print(f"Error forwarding media from channel {channel_id}: {e}")
            bot.send_message(
                message.chat.id,
                "Failed to fetch media from the channel. Please ensure the bot has access to the channel."
            )

    @bot.message_handler(func=lambda msg: msg.text == "Next")
    def next_random_media(message):
        fetch_random_media(message)

    @bot.message_handler(commands=['link'])
    def link_channel(message):
        bot.send_message(
            message.chat.id,
            "To link your channel, please send me the invite link to the channel. "
        )

    # Command to link a channel
    @bot.message_handler(func=lambda m: bool(m.text) and _extract_channel_link(m.text))
    def handle_channel_link(message):
        link = _extract_channel_link(message.text)
        bot.send_message(message.chat.id, "Processing the channel link, please wait…")

        try:
            entity = _join_channel(link)
        except (ChannelPrivateError, InviteHashInvalidError, InviteHashExpiredError):
            bot.send_message(message.chat.id, "I can’t access that channel. Check the invite link and try again.")
            return
        except FloodWaitError as fw:
            bot.send_message(message.chat.id, f"Telegram asked me to wait {fw.seconds}s before joining. Try again later.")
            return
        except Exception as exc:
            logger.exception("Failed to join channel via Telethon")
            bot.send_message(message.chat.id, "Joining the channel failed. Please try again later.")
            return

        channel_id = entity.id
        channel_name = getattr(entity, "title", "Unknown channel")

        databases.add_channel(channel_id, channel_name)
        databases.link_user_to_channel(message.from_user.id, channel_id)

        media_ids = mapping.map_channel_messages(channel_id, bot)
        if not media_ids:
            bot.send_message(message.chat.id, "I couldn’t map any media (maybe the channel forbids forwarding?).")
            return

        bot.send_message(
            message.chat.id,
            f"Joined {channel_name}. Use /random to pull them."
        )
