import main

# Function to map all media messages in a channel
def map_channel_messages(channel_id, bot):
    if channel_id in main.channel_media_map:
        print(f"Channel {channel_id} is already mapped.")
        return main.channel_media_map[channel_id]  # Return cached mapping if it exists

    all_media_ids = []  # List to store media message IDs
    last_message_id = None  # Start with no specific message ID

    try:
        while True:
            # Fetch up to 100 messages starting from the last fetched message
            messages = bot.get_chat_history(
                chat_id=channel_id,
                limit=100,
                offset_id=last_message_id
            )

            if not messages:
                # Break the loop if no more messages are returned
                break

            # Filter messages that contain media and store their IDs
            for msg in messages:
                if msg.content_type in ['photo', 'video', 'document']:
                    all_media_ids.append(msg.message_id)

            # Update the last_message_id to the ID of the last message in the batch
            last_message_id = messages[-1].message_id

        # Cache the mapping for the channel
        main.channel_media_map[channel_id] = all_media_ids
        print(f"Mapped {len(all_media_ids)} media messages for channel {channel_id}")
        return all_media_ids

    except Exception as e:
        print(f"Error mapping messages for channel {channel_id}: {e}")
        return []