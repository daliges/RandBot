import json
from types import SimpleNamespace

import bot.private_handlers as private_handlers
import databases


def _find_handler(bot, command):
    return next(
        entry["handler"]
        for entry in bot.message_handlers
        if entry["commands"] and command in entry["commands"]
    )


def test_set_bot_commands(fake_bot):
    private_handlers.set_bot_commands(fake_bot)
    assert fake_bot.deleted_scopes
    assert fake_bot.commands_set
    commands, scope = fake_bot.commands_set[-1]
    assert [cmd.command for cmd in commands] == ["help", "random", "admin"]


def test_start_with_channel_links_user(monkeypatch, fake_bot):
    private_handlers.register(fake_bot)
    databases.link_user_to_channel = lambda *args, **kwargs: None
    handler = _find_handler(fake_bot, "start")
    message = SimpleNamespace(
        chat=SimpleNamespace(id=50),
        text="/start channel_-1001",
        from_user=SimpleNamespace(id=77),
    )
    fake_bot.register_chat(-1001, "Some Channel")
    handler(message)
    assert "connected to the channel" in fake_bot.sent_messages[-1]["text"]


def test_start_without_link(fake_bot):
    private_handlers.register(fake_bot)
    handler = _find_handler(fake_bot, "start")
    message = SimpleNamespace(
        chat=SimpleNamespace(id=60),
        text="/start",
        from_user=SimpleNamespace(id=88),
    )
    handler(message)
    assert "Use /random" in fake_bot.sent_messages[-1]["text"]


def test_random_requires_link(monkeypatch, fake_bot):
    private_handlers.register(fake_bot)
    handler = _find_handler(fake_bot, "random")
    message = SimpleNamespace(
        chat=SimpleNamespace(id=70),
        from_user=SimpleNamespace(id=22),
    )
    monkeypatch.setattr(databases, "get_user_channel", lambda uid: None)
    handler(message)
    assert "not connected" in fake_bot.sent_messages[-1]["text"]


def test_random_uses_cached_map(monkeypatch, fake_bot, fake_redis):
    channel_id = 555
    private_handlers.register(fake_bot)
    handler = _find_handler(fake_bot, "random")
    fake_redis.hset("channel_media_map", str(channel_id), json.dumps([1, 2]))
    monkeypatch.setattr(databases, "get_user_channel", lambda user_id: channel_id)
    handler(
        SimpleNamespace(
            chat=SimpleNamespace(id=80),
            from_user=SimpleNamespace(id=33),
        )
    )
    assert fake_bot.forwarded_messages
    assert fake_bot.sent_messages[-1]["reply_markup"] is not None
