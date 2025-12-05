from types import SimpleNamespace

import pytest

from bot import channel_watchers
from data import databases


@pytest.fixture(autouse=True)
def reset_channel_locks():
    channel_watchers._channel_locks.clear()
    yield
    channel_watchers._channel_locks.clear()


def test_persist_map_updates_cache(fake_redis):
    channel_id = 1000
    media_ids = [3, 4]

    channel_watchers._persist_map(channel_id, media_ids)
    cached = fake_redis.hget(channel_watchers.MEDIA_CACHE_KEY, str(channel_id))
    assert cached is not None
    assert databases.get_channel_media_map(channel_id) == media_ids


@pytest.mark.asyncio
async def test_handle_new_message_appends(monkeypatch):
    channel_id = 2000
    databases.save_channel_media_map(channel_id, [1, 2])

    event = SimpleNamespace(
        is_channel=True,
        message=SimpleNamespace(id=5, media=True),
        chat_id=channel_id,
    )
    await channel_watchers._handle_new_message(event)

    assert databases.get_channel_media_map(channel_id) == [1, 2, 5]


@pytest.mark.asyncio
async def test_handle_deleted_messages_prunes(monkeypatch):
    channel_id = 3000
    databases.save_channel_media_map(channel_id, [1, 2, 3])

    event = SimpleNamespace(
        is_channel=True,
        chat_id=channel_id,
        deleted_ids=[2, 3],
    )
    await channel_watchers._handle_deleted_messages(event)

    assert databases.get_channel_media_map(channel_id) == [1]
