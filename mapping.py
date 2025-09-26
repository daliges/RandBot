from telethon.sync import TelegramClient
from dotenv import load_dotenv
import app_context, os

load_dotenv()

TELETHON_API_ID = os.getenv("TELETHON_API_ID")
TELETHON_API_HASH = os.getenv("TELETHON_API_HASH")
TELETHON_SESSION_NAME = os.getenv("TELETHON_SESSION_NAME", "telethon_session")

telethon_client = None

try:
    telethon_api_id_int = int(TELETHON_API_ID) if TELETHON_API_ID else None
except (TypeError, ValueError):
    telethon_api_id_int = None
    print("Invalid TELETHON_API_ID; channel mapping will be skipped.")

if telethon_api_id_int and TELETHON_API_HASH:
    telethon_client = TelegramClient(
        TELETHON_SESSION_NAME,
        telethon_api_id_int,
        TELETHON_API_HASH,
    )
    try:
        telethon_client.start()
    except Exception as exc:
        print(f"Failed to start Telethon client: {exc}")
        telethon_client = None
else:
    print("Telethon credentials missing; channel mapping will be skipped.")


async def _collect_media_ids(channel_id: int):
    media_ids = []

    async for message in telethon_client.iter_messages(channel_id, limit=None):
        if message.media:
            media_ids.append(message.id)

    return media_ids


# Function to map all media messages in a channel
def map_channel_messages(channel_id, _):
    if channel_id in app_context.channel_media_map:
        print(f"Channel {channel_id} is already mapped.")
        return app_context.channel_media_map[channel_id]  # Return cached mapping if it exists

    if telethon_client is None:
        print("Telethon client is not configured; cannot map channel.")
        return []

    try:
        all_media_ids = telethon_client.loop.run_until_complete(_collect_media_ids(channel_id))
    except Exception as e:
        print(f"Error mapping messages for channel {channel_id}: {e}")
        return []

    app_context.channel_media_map[channel_id] = all_media_ids
    print(f"Mapped {len(all_media_ids)} media messages for channel {channel_id}")
    return all_media_ids
