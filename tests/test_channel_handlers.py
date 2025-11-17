from types import SimpleNamespace

import bot.channel_handlers as channel_handlers
import databases


def test_handle_admin_promotion_flow(monkeypatch, fake_bot, dummy_threadsafe):
    private_map_called = {"count": 0}
    fake_bot.register_chat(-100, "Channel Name")
    monkeypatch.setattr(databases, "add_channel", lambda cid, name: None)
    monkeypatch.setattr(
        channel_handlers.mapping, "map_channel_messages", lambda cid, bot: private_map_called.__setitem__("count", cid)
    )
    monkeypatch.setattr(
    channel_handlers, "ensure_mapping_account_added", lambda channel_id, bot: True
    )
    monkeypatch.setattr(
        channel_handlers, "send_channel_message_with_deep_link", lambda bot, channel_id: None
    )

    channel_handlers.register(fake_bot)
    handler = fake_bot.member_handlers[0]
    update = SimpleNamespace(
        new_chat_member=SimpleNamespace(status="administrator"),
        chat=SimpleNamespace(id=-100),
    )
    handler(update)
    assert private_map_called["count"] == -100


def test_ignore_non_admin(fake_bot):
    channel_handlers.register(fake_bot)
    handler = fake_bot.member_handlers[0]
    update = SimpleNamespace(
        new_chat_member=SimpleNamespace(status="member"),
        chat=SimpleNamespace(id=-200),
    )
    handler(update)
    assert fake_bot.sent_messages == []
