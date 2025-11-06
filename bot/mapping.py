import asyncio
import app_context


async def _collect_media_ids(channel_id: int) -> list[int]:
    client = app_context.telethon_client
    if client is None:
        return []

    media_ids: list[int] = []
    async for message in client.iter_messages(channel_id, limit=None):
        if message.media:
            media_ids.append(message.id)
    return media_ids


def map_channel_messages(channel_id: int, _) -> list[int]:
    if channel_id in app_context.channel_media_map:
        print(f"Channel {channel_id} is already mapped.")
        return app_context.channel_media_map[channel_id]

    loop = app_context.telethon_loop
    client = app_context.telethon_client
    if not loop or not client:
        print("Telethon client is not configured; cannot map channel.")
        return []

    try:
        future = asyncio.run_coroutine_threadsafe(
            _collect_media_ids(channel_id),
            loop,
        )
        media_ids = future.result()
    except Exception as exc:
        print(f"Error mapping messages for channel {channel_id}: {exc}")
        return []

    app_context.channel_media_map[channel_id] = media_ids
    print(f"Mapped {len(media_ids)} media messages for channel {channel_id}")
    return media_ids
