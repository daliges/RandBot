import app_context, random

bot = app_context.bot  # Assuming 'bot' is defined in main.py as 'bot'

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
        except (IndexError, ValueError) as e:
            print(f"Error parsing deep link: {e}")
            bot.send_message(message.chat.id, "Invalid deep link format.")
            return
        
        # Store the channel_id for the user (in memory for now, use a database for production)
        app_context.user_channel_map[message.from_user.id] = channel_id

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

    # Check if the user is associated with a channel
    if user_id not in app_context.user_channel_map:
        bot.send_message(
            message.chat.id,
            "You are not connected to any channel. Please use the bot via a channel's deep link."
        )
        return

    channel_id = app_context.user_channel_map[user_id]

    # Check if the channel is mapped
    if channel_id not in app_context.channel_media_map:
        bot.send_message(
            message.chat.id,
            "The channel is not mapped yet. Please ensure the bot is added as an admin to the channel."
        )
        return

    # Fetch a random media message ID
    media_ids = app_context.channel_media_map[channel_id]
    if not media_ids:
        bot.send_message(message.chat.id, "No media found in the channel.")
        return

    random_media_id = random.choice(media_ids)

    # Forward the media to the user
    try:
        bot.forward_message(message.chat.id, channel_id, random_media_id)
    except Exception as e:
        print(f"Error forwarding media from channel {channel_id}: {e}")
        bot.send_message(
            message.chat.id,
            "Failed to fetch media from the channel. Please ensure the bot has access to the channel."
        )