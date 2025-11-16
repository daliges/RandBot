import asyncio
import app_context
import databases
import threading


_mapping_locks: dict[int, threading.Lock] = {}
_locks_lock = threading.Lock()


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
    with _locks_lock:
        if channel_id not in _mapping_locks:
            _mapping_locks[channel_id] = threading.Lock()
        lock = _mapping_locks[channel_id]
    
    with lock:
        try:
            if databases.is_channel_in_mappings(channel_id):
                print(f"Channel {channel_id} is already mapped.")
                return databases.get_channel_media_map(channel_id)
        except Exception as exc:
            print(f"Error checking channel mapping: {exc}")
            # Fall through to re-collect if database check fails
        except Exception as exc:
            print(f"Error checking channel mapping: {exc}")
            # Fall through to re-collect if database check fails

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

    databases.save_channel_media_map(channel_id, media_ids)
    print(f"Mapped {len(media_ids)} media messages for channel {channel_id}")
    return media_ids
