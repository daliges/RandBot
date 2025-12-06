import json

import pytest

import bot.private_handlers as private_handlers
from data import databases
from tests.conftest import DummyCallback, DummyMessage


def _channel_id():
    return 555


@pytest.mark.asyncio
async def test_set_bot_commands(fake_bot):
    await private_handlers.set_bot_commands(fake_bot)
    assert fake_bot.deleted_scopes
    commands, scope = fake_bot.commands_set[-1]
    assert [cmd.command for cmd in commands] == ["help", "random", "admin"]


@pytest.mark.asyncio
async def test_start_with_channel_links_user(monkeypatch, fake_bot):
    captured = {}
    monkeypatch.setattr(databases, "link_user_to_channel", lambda uid, cid: captured.setdefault("channel", cid))
    fake_bot.register_chat(-1001, "Some Channel")
    message = DummyMessage(chat_id=50, user_id=77, text="/start channel_-1001")
    await private_handlers.start(message, fake_bot)
    assert captured["channel"] == -1001
    assert any("channel is connected to the bot now" in reply["text"] for reply in message.replies)


@pytest.mark.asyncio
async def test_start_without_link(fake_bot):
    message = DummyMessage(chat_id=60, user_id=88, text="/start")
    await private_handlers.start(message, fake_bot)
    assert any("Use /random" in reply["text"] for reply in message.replies)


@pytest.mark.asyncio
async def test_random_uses_cached_map(monkeypatch, fake_bot, fake_redis):
    channel_id = _channel_id()
    fake_bot.register_chat(channel_id, "Some Channel", username="channel")
    fake_redis.setex(private_handlers.CHANNEL_IDS_CACHE_KEY, 100, json.dumps([channel_id]))
    fake_redis.hset(private_handlers.MEDIA_CACHE_KEY, str(channel_id), json.dumps([1, 2]))
    message = DummyMessage(chat_id=80, user_id=33, text="/random")
    await private_handlers.fetch_random_media(message, fake_bot)
    assert fake_bot.copied_messages
    assert fake_bot.copied_messages[-1]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_subscribe_shows_alert_for_existing_member(monkeypatch, fake_bot):
    channel_id = _channel_id()
    fake_bot.register_chat(channel_id, "Channel", username="channel")
    fake_bot.set_chat_member(channel_id, 99, private_handlers.ChatMemberStatus.MEMBER)
    callback = DummyCallback(data=f"subscribe:{channel_id}", from_user=99, message=DummyMessage(chat_id=1))
    await private_handlers.handle_subscribe(callback, fake_bot)
    assert callback.answers[-1]["show_alert"] is True
