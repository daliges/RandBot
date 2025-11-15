import json
from telebot import TeleBot, logger, types
from telebot.types import BotCommand, BotCommandScopeDefault
import app_context, random, databases
from databases import redis_client

# Set up bot commands for the side menu
def set_bot_commands(bot: TeleBot) -> None:
    commands = [
        BotCommand("help", "Help and information about the bot"),
        BotCommand("random", "Get random media from the channel")
    ]
    bot.set_my_commands(commands, scope=BotCommandScopeDefault())

def register(bot: TeleBot) -> None:
    @bot.message_handler(commands=['help'])
    def help(message):
        bot.send_message(
            message.chat.id,
            "Hello! I'm your Random bot. Use /random to get random media from the channel in private chat with me."
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

            else:
                media_map = json.loads(redis_client.hget("channel_media_map", str(channel_id)))

        except Exception as exc:
            logger.exception("Failed to read media map for channel %s", channel_id)
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
