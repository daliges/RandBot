import asyncio
import json
import logging
from typing import Sequence

from telethon import events

import databases

logger = logging.getLogger(__name__)

MEDIA_CACHE_KEY = "channel_media_map"
_channel_locks: dict[int, asyncio.Lock] = {}


def register(client) -> None:
    """Attach listeners that incrementally maintain channel mappings."""
    client.add_event_handler(_handle_new_message, events.NewMessage())
    client.add_event_handler(_handle_deleted_messages, events.MessageDeleted())


async def _handle_new_message(event) -> None:
    if not getattr(event, "is_channel", False):
        return
    message = getattr(event, "message", None)
    if not message or not getattr(message, "media", None):
        return

    channel_id = getattr(event, "chat_id", None)
    if channel_id is None or not await asyncio.to_thread(
        databases.is_channel_in_mappings, channel_id
    ):
        return

    message_id = message.id
    lock = _channel_locks.setdefault(channel_id, asyncio.Lock())
    async with lock:
        media_map = await asyncio.to_thread(databases.get_channel_media_map, channel_id)
        if message_id in media_map:
            return

        media_map.append(message_id)
        media_map.sort()
        await _persist_map_async(channel_id, media_map)
    logger.info("Tracked new media %s for channel %s", message_id, channel_id)


async def _handle_deleted_messages(event) -> None:
    if not getattr(event, "is_channel", False):
        return

    channel_id = getattr(event, "chat_id", None) or getattr(event, "channel_id", None)
    if channel_id is None or not await asyncio.to_thread(
        databases.is_channel_in_mappings, channel_id
    ):
        return

    deleted_ids: Sequence[int] = getattr(event, "deleted_ids", ()) or ()
    if not deleted_ids:
        return

    lock = _channel_locks.setdefault(channel_id, asyncio.Lock())
    async with lock:
        media_map = await asyncio.to_thread(databases.get_channel_media_map, channel_id)
        deleted_set = set(deleted_ids)
        updated = [mid for mid in media_map if mid not in deleted_set]
        if len(updated) == len(media_map):
            return

        await _persist_map_async(channel_id, updated)
    logger.info(
        "Removed %s media items for channel %s",
        len(media_map) - len(updated),
        channel_id,
    )


def _persist_map(channel_id: int, media_ids: list[int]) -> None:
    databases.save_channel_media_map(channel_id, media_ids)
    try:
        serialized = json.dumps(media_ids)
        databases.redis_client.hset(MEDIA_CACHE_KEY, str(channel_id), serialized)
    except Exception as exc:
        logger.warning("Failed to refresh Redis cache for %s: %s", channel_id, exc)


async def _persist_map_async(channel_id: int, media_ids: list[int]) -> None:
    await asyncio.to_thread(_persist_map, channel_id, media_ids)
